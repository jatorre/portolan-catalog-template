#!/usr/bin/env python3
"""Generate the catalog's STAC + OGC API - Records documents from compact descriptors.

Inputs (committed in the repo):
  portolan.config.json         publisher + bucket config
  datasets/<id>.json           one compact descriptor per dataset (see schema below)

Outputs (written, then committed; publish.py mirrors them to the bucket):
  catalog.json                 STAC Catalog
  items/<id>.json              STAC Item per dataset
  records/catalog.json         OGC API - Records catalogue
  records/<id>.json            OGC API - Records record per dataset

Descriptor schema (datasets/<id>.json):
  id, title, description, keywords[], bbox[w,s,e,n], license, provider,
  semantics{spec,label,describes,answers,unit},
  representation: "iceberg" | "raquet" | "remote-geoparquet",
  tables: ["v2.x","v3.x"]      # iceberg: namespace.table(s); first = primary
  href: "<url>"                # raquet / remote-geoparquet: the data URL
  provenance{...}              # optional
"""
import json, os, glob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
C = json.load(open("portolan.config.json"))
BASE = C["public_base"].rstrip("/")
REC_CORE = "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/record-core"


def geom_from_bbox(b):
    w, s, e, n = b
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def assets_for(d):
    """STAC assets dict for a dataset descriptor."""
    rep = d.get("representation", "iceberg")
    if rep == "iceberg":
        tables = d["tables"]
        out = {}
        names = ["data", "data_native", "data_3", "data_4"]
        for i, t in enumerate(tables):
            ns, tbl = t.split(".")
            out[names[i] if i < len(names) else f"data_{i}"] = {
                "href": f"{BASE}/data/{ns}/{tbl}/metadata/v1.metadata.json",
                "type": "application/vnd.apache.iceberg+json", "roles": ["data"],
                "title": f"Apache Iceberg table {t} — iceberg_scan() or ATTACH the catalog endpoint",
                "portolan:access": "iceberg_scan",
                "portolan:iceberg_table": t,
                "portolan:iceberg_endpoint": BASE,
            }
        return out
    if rep == "raquet":
        return {"data": {"href": d["href"], "type": "application/octet-stream",
                         "roles": ["data"], "title": "Raquet raster — read_raquet()",
                         "portolan:access": "read_raquet"}}
    # remote-geoparquet
    return {"data": {"href": d["href"], "type": "application/vnd.apache.parquet",
                     "roles": ["data"], "title": "Remote GeoParquet — read in place",
                     "portolan:access": "read_parquet"}}


def stac_item(d):
    p = {"title": d.get("title", d["id"]), "description": d.get("description", ""),
         "keywords": d.get("keywords", []), "crs": d.get("crs", "OGC:CRS84"),
         "materialized": True, "provider": d.get("provider", C.get("data_provider", "")),
         "license": d.get("license", C.get("data_license", "")), "datetime": None}
    if d.get("semantics"):
        p["semantics"] = d["semantics"]
    if d.get("provenance"):
        p["portolan:provenance"] = d["provenance"]
    return {"type": "Feature", "stac_version": "1.1.0", "id": d["id"],
            "bbox": d["bbox"], "geometry": geom_from_bbox(d["bbox"]),
            "properties": p, "assets": assets_for(d),
            "links": [
                {"rel": "root", "href": f"{BASE}/catalog.json", "type": "application/json"},
                {"rel": "parent", "href": f"{BASE}/catalog.json", "type": "application/json"},
                {"rel": "alternate", "href": f"{BASE}/records/{d['id']}.json",
                 "type": "application/geo+json", "title": "Same record as OGC API - Records"},
            ]}


def records_record(d):
    primary = (d.get("tables") or [None])[0]
    props = {"type": "dataset", "title": d.get("title", d["id"]),
             "description": d.get("description", ""), "keywords": d.get("keywords", []),
             "contacts": [{"name": d.get("provider", C.get("data_provider", "")), "roles": ["provider"]}],
             "license": d.get("license", C.get("data_license", ""))}
    if d.get("semantics"):
        props["themes"] = [{"scheme": d["semantics"].get("spec_uri", "https://opensemanticinterchange.org"),
                            "concepts": [{"id": d["semantics"].get("answers", d["id"])}]}]
    if primary:
        props["portolan:iceberg_endpoint"] = BASE
        props["portolan:iceberg_table"] = primary
    if d.get("provenance"):
        props["portolan:provenance"] = d["provenance"]
    links = [{"rel": "root", "href": f"{BASE}/records/catalog.json", "type": "application/json"},
             {"rel": "self", "href": f"{BASE}/records/{d['id']}.json", "type": "application/geo+json"}]
    for a in assets_for(d).values():
        links.append({"rel": "item", "href": a["href"], "type": a["type"], "title": a.get("title", "")})
    return {"id": d["id"], "type": "Feature", "conformsTo": [REC_CORE], "time": None,
            "bbox": d["bbox"], "geometry": geom_from_bbox(d["bbox"]), "properties": props, "links": links}


def union_bbox(ds):
    bs = [d["bbox"] for d in ds if d.get("bbox")]
    if not bs:
        return None
    return [min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[2] for b in bs), max(b[3] for b in bs)]


def main():
    descs = [json.load(open(f)) for f in sorted(glob.glob("datasets/*.json"))]
    if not descs:
        raise SystemExit("no datasets/*.json descriptors found")
    os.makedirs("items", exist_ok=True)
    os.makedirs("records", exist_ok=True)

    contributions = {"via": "github", "repo": C.get("contributions_repo", C.get("repo", "")),
                     "issues_url": C.get("contributions_issues_url", ""),
                     "accepts": ["issue", "pull_request"]}
    ub = union_bbox(descs)
    cat = {"type": "Catalog", "stac_version": "1.0.0", "id": C["alias"],
           "title": f"{C.get('flag','')} {C['publisher']} (Portolan catalog)".strip(),
           "description": C.get("description",
               f"A Portolan catalog: git-sourced STAC + Apache Iceberg metadata, published to "
               f"object storage as a static Iceberg REST catalog (ATTACH) + STAC + OGC API - Records "
               f"+ direct download. Data from {C.get('data_provider', C['publisher'])}."),
           "portolan:catalog_type": "iceberg-rest-static",
           "portolan:iceberg_endpoint": BASE,
           "portolan:datasets": len(descs),
           "portolan:contributions": contributions,
           "links": [
               {"rel": "root", "href": f"{BASE}/catalog.json", "type": "application/json"},
               {"rel": "self", "href": f"{BASE}/catalog.json", "type": "application/json"},
               {"rel": "alternate", "href": f"{BASE}/records/catalog.json",
                "type": "application/json", "title": "Same catalogue as OGC API - Records"},
               {"rel": "feedback", "href": contributions["issues_url"], "type": "text/html",
                "title": "Report issues or contribute data"},
           ]}
    if ub:
        cat["extent"] = {"spatial": {"bbox": [ub]}}
    for d in descs:
        cat["links"].append({"rel": "item", "href": f"{BASE}/items/{d['id']}.json",
                             "type": "application/geo+json", "title": d.get("title", d["id"])})
        json.dump(stac_item(d), open(f"items/{d['id']}.json", "w"), indent=2, ensure_ascii=False)
        json.dump(records_record(d), open(f"records/{d['id']}.json", "w"), indent=2, ensure_ascii=False)
    json.dump(cat, open("catalog.json", "w"), indent=2, ensure_ascii=False)

    rec_cat = {"id": C["alias"], "type": "Catalog",
               "conformsTo": ["http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/core", REC_CORE],
               "title": f"{C.get('flag','')} {C['publisher']} (OGC API - Records catalogue)".strip(),
               "description": "OGC API - Records view of this Portolan catalogue (same GeoJSON model as the STAC view).",
               "links": [{"rel": "self", "href": f"{BASE}/records/catalog.json", "type": "application/json"},
                         {"rel": "alternate", "href": f"{BASE}/catalog.json", "type": "application/json",
                          "title": "Same catalogue as a STAC Catalog"}]}
    for d in descs:
        rec_cat["links"].append({"rel": "items", "href": f"{BASE}/records/{d['id']}.json",
                                "type": "application/geo+json", "title": d.get("title", d["id"])})
    json.dump(rec_cat, open("records/catalog.json", "w"), indent=2, ensure_ascii=False)
    print(f"generated catalog.json + {len(descs)} item(s) + records/ for {C['publisher']}")


if __name__ == "__main__":
    main()
