"""Kourovka Notebook (arXiv:1401.0300, 21st ed.) -> problems with number, edition, proposer, statement, answer, answer years."""
import json, re, sys
t = open(sys.argv[1], errors="ignore").read()
ED_YEAR = {1:1965,2:1966,3:1969,4:1973,5:1976,6:1978,7:1980,8:1982,9:1984,10:1986,11:1990,12:1992,13:1995,14:1999,
           15:2002,16:2006,17:2010,18:2014,19:2018,20:2022,21:2026}
out = []
arch = t.find("\\label{archiv}")
for bm in re.finditer(r"\\bmp(.*?)\\(?:emp|rmp)", t, re.S):
    b, archived = bm.group(1), bm.start() > arch
    m = re.search(r"\\textbf\{(\d+)\.(\d+)\.?\}", b)
    if not m:
        continue
    ed, k = int(m.group(1)), m.group(2)
    body = b[m.end():]
    ans = ""
    a = re.search(r"\\otv(.*)", body, re.S)
    if a:
        ans, body = a.group(1), body[:a.start()]
    pr = re.search(r"\\sl\s+([^}]+)\}", body)
    if archived and not ans and pr:
        ans, body = body[pr.end():], body[:pr.end()]
    stmt = re.sub(r"\\hfill.*", "", body, flags=re.S)
    years = [int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", ans)]
    arx = re.findall(r"(\d{4}\.\d{4,5}|math/\d{7})", ans)
    out.append({"id": f"{ed}.{k}", "edition": ed, "year_posed": ED_YEAR.get(ed), "proposer": pr.group(1).strip() if pr else "",
                "statement": " ".join(stmt.split())[:3000], "answer": " ".join(ans.split())[:2000],
                "solved": bool(ans.strip()), "archived": archived, "answer_year": min(years) if years else None, "answer_arxiv": arx})
json.dump(out, open(sys.argv[2], "w"), indent=0)
s = [p for p in out if p["solved"]]
print(len(out), "problems;", len(s), "with answers;", sum(1 for p in s if p["answer_arxiv"]), "answers cite arXiv")
