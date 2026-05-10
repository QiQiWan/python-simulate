from __future__ import annotations
_REGISTRY={}
def register_interface_generator(key, factory=None):
    def deco(fn): _REGISTRY[str(key)]=fn; return fn
    return deco(factory) if factory is not None else deco
def registered_interface_generators(): return dict(_REGISTRY)
def resolve_registered_interface_generator(key, *args, **kwargs): return _REGISTRY[str(key)](*args, **kwargs)
