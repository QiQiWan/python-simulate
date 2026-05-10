from __future__ import annotations

def collect_region_point_ids(model, region_names=()): return {str(r): tuple() for r in tuple(region_names or ())}
def resolve_region_selector(model, selector): return tuple(getattr(selector, 'names', ()) or ())
def union_region_names(*groups):
    out=[]
    for group in groups:
        for name in tuple(group or ()): 
            if str(name) not in out: out.append(str(name))
    return tuple(out)
