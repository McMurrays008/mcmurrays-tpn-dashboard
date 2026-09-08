"""
Read the TPN Export To Excel workbook using Python's standard library only.
No Excel installation, pandas or openpyxl is required on the collector PC.

The parser searches worksheets for the TPN headers and emits data.js.
"""
from __future__ import annotations
import json, re, sys, zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

MAIN_SERVICES={"AM","AMTL","BKSL","BSTL","ND","NDTL","PM","PMTL","TIME","TMTL"}
RISK_STATUSES={"ACH","ATH","ATHP","ICC","ITD","ITDP","ITH","ITHP","OFDP","WCD","WCDP","WDDP"}

NS={"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
RELNS={"p":"http://schemas.openxmlformats.org/package/2006/relationships"}

def col_index(cell_ref):
    letters=re.match(r"[A-Z]+", cell_ref).group(0)
    n=0
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
    t=c.attrib.get("t")
    v=c.find("m:v",NS)
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
    root=ET.fromstring(z.read(path))
    rows=[]
    for row in root.findall(".//m:sheetData/m:row",NS):
        vals={}
        for c in row.findall("m:c",NS):
            vals[col_index(c.attrib["r"])]=cell_value(c,ss)
        if vals:
            mx=max(vals)
            rows.append([vals.get(i,"") for i in range(mx+1)])
    return rows

def clean(h):
    return str(h or "").lstrip("\ufeff").removeprefix("ï»¿").strip()

def pick_table(xlsx):
    with zipfile.ZipFile(xlsx) as z:
        ss=shared_strings(z)
        for sheet_name,path in workbook_sheets(z):
            rows=sheet_rows(z,path,ss)
            for i,row in enumerate(rows[:30]):
                headers=[clean(x) for x in row]
                header_set=set(headers)
                # Support current CSV-style names and likely Excel export names.
                if "Docket" in header_set and ("Sender" in header_set or "Consignor" in header_set) and "Status" in header_set:
                    width=len(headers)
                    out=[]
                    for rr in rows[i+1:]:
                        rr=rr+[""]*(width-len(rr))
                        if any(str(x).strip() for x in rr[:width]):
                            out.append(dict(zip(headers,rr[:width])))
                    return sheet_name,out
    raise RuntimeError("Could not find TPN consignment table in workbook.")

def first(r,*names):
    for n in names:
        if n in r and str(r[n]).strip()!="": return str(r[n]).strip()
    return ""

def as_int(v):
    try:return int(float(str(v).strip() or 0))
    except:return 0

def build(xlsx,outfile):
    sheet,rows=pick_table(xlsx)
    data=[]
    for r in rows:
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
    snap={"source":Path(xlsx).name,"sheet":sheet,
          "generated_at":datetime.now().astimezone().isoformat(timespec="seconds"),"rows":data}
    Path(outfile).write_text("window.TPN_SNAPSHOT = "+json.dumps(snap,ensure_ascii=False)+";\n",encoding="utf-8")
    print(f"Updated {outfile} from {xlsx}: {len(data)} consignments")
if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("Usage: python build_data_from_xlsx.py export.xlsx data.js")
    build(sys.argv[1],sys.argv[2])
