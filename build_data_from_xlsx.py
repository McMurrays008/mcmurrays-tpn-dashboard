"""
TPN export parser for both modern .xlsx files and legacy .xls downloads.

Supported inputs:
- OOXML .xlsx (ZIP container)
- Binary BIFF .xls via xlrd
- HTML tables saved with .xls extension
- SpreadsheetML 2003 XML saved with .xls extension

The parser searches for the TPN consignment header row, applies the Browse rule
Req = 8 AND Del != 8 locally, and emits data.js.
"""
from __future__ import annotations
import json, re, sys, zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from html.parser import HTMLParser

MAIN_SERVICES={"AM","AMTL","BKSL","BSTL","ND","NDTL","PM","PMTL","TIME","TMTL"}
RISK_STATUSES={"ACH","ATH","ATHP","ICC","ITD","ITDP","ITH","ITHP","OFDP","WCD","WCDP","WDDP"}

NS={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def clean(h):
    return str(h or "").lstrip("\ufeff").removeprefix("ï»¿").strip()


def normalize_cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def find_tpn_table(sheet_name, rows):
    for i,row in enumerate(rows[:60]):
        headers=[clean(x) for x in row]
        header_set=set(headers)
        if "Docket" in header_set and ("Sender" in header_set or "Consignor" in header_set) and "Status" in header_set:
            width=len(headers)
            out=[]
            for rr in rows[i+1:]:
                rr=list(rr)+[""]*(width-len(rr))
                rr=[normalize_cell(x) for x in rr[:width]]
                if any(x.strip() for x in rr):
                    out.append(dict(zip(headers,rr)))
            return sheet_name,out
    return None

# ---------- XLSX ----------
def col_index(cell_ref):
    m=re.match(r"[A-Z]+", cell_ref or "")
    if not m: return 0
    letters=m.group(0); n=0
    for ch in letters: n=n*26+ord(ch)-64
    return n-1


def shared_strings(z):
    try: root=ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError: return []
    out=[]
    for si in root.findall("m:si",NS):
        out.append("".join(t.text or "" for t in si.iter("{%s}t"%NS["m"])))
    return out


def workbook_sheets(z):
    wb=ET.fromstring(z.read("xl/workbook.xml"))
    rel=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets={x.attrib["Id"]:x.attrib["Target"] for x in rel}
    result=[]
    for sh in wb.find("m:sheets",NS):
        rid=sh.attrib["{%s}id"%NS["r"]]
        target=targets[rid].lstrip("/")
        if not target.startswith("xl/"): target="xl/"+target
        result.append((sh.attrib["name"],target))
    return result


def cell_value(c, ss):
    t=c.attrib.get("t"); v=c.find("m:v",NS)
    if t=="inlineStr":
        x=c.find("m:is",NS)
        return "" if x is None else "".join(n.text or "" for n in x.iter("{%s}t"%NS["m"]))
    if v is None:return ""
    val=v.text or ""
    if t=="s":
        try:return ss[int(val)]
        except:return val
    return val


def sheet_rows(z,path,ss):
    root=ET.fromstring(z.read(path)); rows=[]
    for row in root.findall(".//m:sheetData/m:row",NS):
        vals={}
        for c in row.findall("m:c",NS): vals[col_index(c.attrib.get("r","A1"))]=cell_value(c,ss)
        if vals:
            mx=max(vals); rows.append([vals.get(i,"") for i in range(mx+1)])
    return rows


def parse_xlsx(path):
    with zipfile.ZipFile(path) as z:
        ss=shared_strings(z)
        for sheet_name,sheet_path in workbook_sheets(z):
            found=find_tpn_table(sheet_name,sheet_rows(z,sheet_path,ss))
            if found:return found
    return None

# ---------- binary XLS ----------
def parse_binary_xls(path):
    try:
        import xlrd
    except ImportError as e:
        raise RuntimeError("Binary .xls detected but xlrd is not installed") from e
    book=xlrd.open_workbook(path, on_demand=True)
    try:
        for sh in book.sheets():
            rows=[]
            for r in range(sh.nrows):
                rows.append([normalize_cell(sh.cell_value(r,c)) for c in range(sh.ncols)])
            found=find_tpn_table(sh.name,rows)
            if found:return found
    finally:
        try: book.release_resources()
        except Exception: pass
    return None

# ---------- HTML saved as XLS ----------
class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables=[]; self.table=None; self.row=None; self.cell=None; self.in_cell=False
    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag=="table": self.table=[]
        elif tag=="tr" and self.table is not None: self.row=[]
        elif tag in ("td","th") and self.row is not None:
            self.cell=[]; self.in_cell=True
        elif tag=="br" and self.in_cell: self.cell.append(" ")
    def handle_data(self,data):
        if self.in_cell and self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        tag=tag.lower()
        if tag in ("td","th") and self.in_cell:
            self.row.append(clean("".join(self.cell))); self.cell=None; self.in_cell=False
        elif tag=="tr" and self.row is not None:
            self.table.append(self.row); self.row=None
        elif tag=="table" and self.table is not None:
            self.tables.append(self.table); self.table=None


def parse_html_xls(path):
    raw=Path(path).read_bytes()
    for enc in ("utf-8-sig","cp1252","latin1"):
        try: text=raw.decode(enc); break
        except UnicodeDecodeError: continue
    p=TableParser(); p.feed(text)
    for i,rows in enumerate(p.tables,1):
        found=find_tpn_table(f"HTML table {i}",rows)
        if found:return found
    return None

# ---------- SpreadsheetML 2003 ----------
def parse_spreadsheetml(path):
    root=ET.parse(path).getroot()
    # Namespace varies, so match by local-name.
    def lname(el): return el.tag.rsplit('}',1)[-1]
    for wi,ws in enumerate([e for e in root.iter() if lname(e)=="Worksheet"],1):
        name=ws.attrib.get("{urn:schemas-microsoft-com:office:spreadsheet}Name") or ws.attrib.get("Name") or f"Worksheet {wi}"
        rows=[]
        for row in [e for e in ws.iter() if lname(e)=="Row"]:
            vals=[]
            for cell in [e for e in row if lname(e)=="Cell"]:
                idx=cell.attrib.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
                if idx:
                    target=int(idx)-1
                    while len(vals)<target: vals.append("")
                data=next((d for d in cell.iter() if lname(d)=="Data"),None)
                vals.append(clean("" if data is None else "".join(data.itertext())))
            rows.append(vals)
        found=find_tpn_table(name,rows)
        if found:return found
    return None


def detect_and_parse(path):
    p=Path(path); head=p.read_bytes()[:512]
    errors=[]
    # OOXML/ZIP
    if head.startswith(b"PK"):
        try:
            found=parse_xlsx(path)
            if found:return found,"xlsx"
        except Exception as e: errors.append(f"xlsx: {type(e).__name__}: {e}")
    # OLE Compound File binary xls
    if head.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        try:
            found=parse_binary_xls(path)
            if found:return found,"xls-biff"
        except Exception as e: errors.append(f"xls-biff: {type(e).__name__}: {e}")
    # Text formats with .xls extension are common in older web exports.
    stripped=head.lstrip().lower()
    if stripped.startswith(b"<"):
        try:
            found=parse_spreadsheetml(path)
            if found:return found,"spreadsheetml"
        except Exception as e: errors.append(f"spreadsheetml: {type(e).__name__}: {e}")
        try:
            found=parse_html_xls(path)
            if found:return found,"html-xls"
        except Exception as e: errors.append(f"html-xls: {type(e).__name__}: {e}")
    # Last-chance fallbacks, regardless of signature.
    for label,fn in (("xls-biff",parse_binary_xls),("html-xls",parse_html_xls),("spreadsheetml",parse_spreadsheetml)):
        try:
            found=fn(path)
            if found:return found,label
        except Exception as e: errors.append(f"{label}: {type(e).__name__}: {e}")
    raise RuntimeError("Could not find TPN consignment table. Parser attempts: " + " | ".join(errors[-6:]))


def first(r,*names):
    for n in names:
        if n in r and str(r[n]).strip()!="": return str(r[n]).strip()
    return ""


def as_int(v):
    try:return int(float(str(v).strip() or 0))
    except:return 0


def build(infile,outfile):
    (sheet,rows),fmt=detect_and_parse(infile)
    data=[]; skipped=0
    for r in rows:
        req=first(r,"Req","Request")
        deliver_raw=first(r,"Del","Deliver","Delivery Depot")
        # Apply only when those fields are present. This preserves compatibility
        # with exports that are already pre-filtered.
        if req and req != "8": skipped+=1; continue
        if deliver_raw == "8": skipped+=1; continue

        docket=first(r,"Docket","Consignment","Consignment Number")
        sender=first(r,"Sender","Consignor")
        service=first(r,"Service")
        status=first(r,"Status","Status Code")
        pallets=as_int(first(r,"Pallets","Pallet"))
        consignee=first(r,"Consignee")
        postcode=first(r,"Post Code","Postcode")
        depot=first(r,"Deliver","Delivery Depot","Del")
        if not docket and not sender and not consignee: continue
        data.append({
            "Docket":docket,"Sender":sender,"Service":service,"Status":status,
            "Pallets":pallets,"Consignee":consignee,"Postcode":postcode,"DeliveryDepot":depot,
            "Live":status!="DEL",
            "Risk":service in MAIN_SERVICES and status in RISK_STATUSES,
            "NoScans":status=="CRE",
            "WDD":service in MAIN_SERVICES and status=="WDD",
            "Undelivered":service in MAIN_SERVICES and status!="DEL"
        })
    snap={"source":Path(infile).name,"source_format":fmt,"sheet":sheet,
          "generated_at":datetime.now().astimezone().isoformat(timespec="seconds"),"rows":data}
    Path(outfile).write_text("window.TPN_SNAPSHOT = "+json.dumps(snap,ensure_ascii=False)+";\n",encoding="utf-8")
    print(f"Updated {outfile} from {infile} [{fmt}]: {len(data)} consignments after Req=8 / Del!=8 filter; skipped {skipped}")

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: python build_data_from_xlsx.py export.xls[x] data.js")
    build(sys.argv[1],sys.argv[2])
