import json, re, sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
import pandas as pd

ALIASES = {
  "docket":["docket","consignment","consignmentnumber"], "createdDate":["createddate","created"],
  "account":["account","accountcode"], "sender":["sender","customer"], "consignee":["consignee"],
  "postCode":["postcode","postalcode"], "service":["service"], "pallets":["pallets","pallet"],
  "customerReference":["customerreference","customerref","reference"], "status":["status","scanstatus"],
  "request":["request","req"], "collect":["collect","col"]
}

def key(v): return re.sub(r"[^a-z0-9]", "", str(v).lower())
def scalar(v):
  if pd.isna(v): return ""
  if hasattr(v, "isoformat"): return v.isoformat()
  if isinstance(v, float) and v.is_integer(): return int(v)
  return v.item() if hasattr(v, "item") else v

def clean(v): return str(v or "").lstrip("\ufeff").removeprefix("ï»¿").strip()

class TableParser(HTMLParser):
  def __init__(self):
    super().__init__(convert_charrefs=True); self.tables=[]; self.table=None; self.row=None; self.cell=None
  def handle_starttag(self, tag, attrs):
    tag=tag.lower()
    if tag=="table": self.table=[]
    elif tag=="tr" and self.table is not None: self.row=[]
    elif tag in ("td","th") and self.row is not None: self.cell=[]
    elif tag=="br" and self.cell is not None: self.cell.append(" ")
  def handle_data(self, data):
    if self.cell is not None: self.cell.append(data)
  def handle_endtag(self, tag):
    tag=tag.lower()
    if tag in ("td","th") and self.cell is not None:
      self.row.append(clean("".join(self.cell))); self.cell=None
    elif tag=="tr" and self.row is not None:
      self.table.append(self.row); self.row=None
    elif tag=="table" and self.table is not None:
      self.tables.append(self.table); self.table=None

def table_frame(rows):
  for i,row in enumerate(rows[:60]):
    headers=[clean(v) for v in row]
    normalized={key(v) for v in headers}
    if "docket" in normalized and "status" in normalized and ({"request","req"} & normalized):
      width=len(headers)
      data=[]
      for values in rows[i+1:]:
        values=list(values)+[""]*width
        if any(clean(v) for v in values[:width]): data.append(values[:width])
      return pd.DataFrame(data,columns=headers)
  return None

def read_tpn_export(src):
  errors=[]
  try:
    raw=pd.read_excel(src,sheet_name=0,header=None)
    found=table_frame(raw.fillna("").values.tolist())
    if found is not None: return found
  except Exception as e: errors.append(f"excel: {type(e).__name__}: {e}")
  blob=Path(src).read_bytes()
  text=None
  for encoding in ("utf-8-sig","cp1252","latin1"):
    try: text=blob.decode(encoding); break
    except UnicodeDecodeError: pass
  if text:
    try:
      parser=TableParser(); parser.feed(text)
      for rows in parser.tables:
        found=table_frame(rows)
        if found is not None: return found
    except Exception as e: errors.append(f"html: {type(e).__name__}: {e}")
    try:
      root=ET.fromstring(text)
      def local(el): return el.tag.rsplit("}",1)[-1]
      for worksheet in (el for el in root.iter() if local(el)=="Worksheet"):
        rows=[]
        for row in (el for el in worksheet.iter() if local(el)=="Row"):
          values=[]
          for cell in (el for el in row if local(el)=="Cell"):
            index=next((v for k,v in cell.attrib.items() if k.endswith("}Index") or k=="Index"),None)
            if index:
              while len(values)<int(index)-1: values.append("")
            data=next((el for el in cell.iter() if local(el)=="Data"),None)
            values.append(clean("" if data is None else "".join(data.itertext())))
          rows.append(values)
        found=table_frame(rows)
        if found is not None: return found
    except Exception as e: errors.append(f"xml: {type(e).__name__}: {e}")
  raise RuntimeError("Could not find the TPN consignment table: "+" | ".join(errors))

def main(src, out):
  df = read_tpn_export(src)
  columns = {key(c):c for c in df.columns}
  def col(name, required=True):
    for alias in ALIASES[name]:
      if alias in columns: return columns[alias]
    if required: raise RuntimeError(f"Missing TPN export column: {name}")
  req, collect = col("request"), col("collect")
  req_values = pd.to_numeric(df[req], errors="coerce")
  col_values = pd.to_numeric(df[collect], errors="coerce")
  df = df[(req_values == 8) & (col_values == 8)].copy()
  fields = ["docket","createdDate","account","sender","consignee","postCode","service","pallets","customerReference","status"]
  mapping = {f:col(f, required=f not in {"customerReference"}) for f in fields}
  rows=[]
  for _, r in df.iterrows():
    item={f:scalar(r[c]) if c else "" for f,c in mapping.items()}
    item["status"] = str(item["status"] or "Unknown").strip().upper()
    rows.append(item)
  if not rows:
    raise RuntimeError("Export contained no consignments matching Req = 008 and Col = 008; existing dashboard data preserved")
  meta={"updatedAt":datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="seconds"),"consignments":len(rows)}
  payload="window.TPN_META="+json.dumps(meta,separators=(",",":"))+";\n"
  payload+="window.TPN_DATA="+json.dumps(rows, ensure_ascii=False, separators=(",",":"))+";\n"
  Path(out).write_text(payload, encoding="utf-8")
  print(f"Updated {out}: {len(rows)} consignments after Req=008 / Col=008 filter", flush=True)

if __name__ == "__main__":
  main(sys.argv[1], sys.argv[2])
