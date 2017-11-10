from importlib import import_module
from importlib import reload as reload_module
from importlib import invalidate_caches as invalidate_caches

from types import ModuleType

import importlib.util

import inspect, sys, os
from time import sleep

import tyk.decorators as decorators
from tyk.loader import MiddlewareLoader
from gateway import TykGateway as tyk

HandlerDecorators = list( map( lambda m: m[1], inspect.getmembers(decorators, inspect.isclass) ) )

class TykMiddleware:
    def __init__(self, filepath, bundle_root_path=None):
        tyk.log( "Loading module: '{0}'".format(filepath), "info")
        self.filepath = filepath
        self.handlers = {}

        self.bundle_id = filepath
        self.bundle_root_path = bundle_root_path

        self.imported_modules = []
        
        module_splits = filepath.split('_')
        self.api_id, self.middleware_id = module_splits[0], module_splits[1]

        self.module_path = os.path.join(self.bundle_root_path, filepath)
        self.mw_path = self.module_path + "/middleware.py"

        try:
            self.loader = MiddlewareLoader(self)
            sys.meta_path.append(self.loader)
            invalidate_caches()
            spec = importlib.util.spec_from_file_location(filepath, location=self.mw_path, submodule_search_locations=[self.module_path])
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
            self.register_handlers()
            self.cleanup()
        except:
            tyk.log_error( "Middleware initialization error:" )

    def register_handlers(self):
        new_handlers = {}
        for attr in dir(self.module):
            attr_value = getattr(self.module, attr)
            if callable(attr_value):
                attr_type = type(attr_value)
                if attr_type in HandlerDecorators:
                    handler_type = attr_value.__class__.__name__.lower()
                    if handler_type not in new_handlers:
                        new_handlers[handler_type] = []
                    new_handlers[handler_type].append(attr_value)
        self.handlers = new_handlers

    def build_hooks_and_event_handlers(self):
        hooks = {}
        for hook_type in self.handlers:
            for handler in self.handlers[hook_type]:
                handler.middleware = self
                hooks[handler.name] = handler
        return hooks

    def cleanup(self):
        sys.meta_path.pop()
        for m in self.imported_modules:
            del sys.modules[m]

    def process(self, handler, object):
        handlerType = type(handler)

        if handlerType == decorators.Event:
            handler(object, object.spec)
            return
        elif handler.arg_count == 4:
            object.request, object.session, object.metadata = handler(object.request, object.session, object.metadata, object.spec)
        elif handler.arg_count == 3:
            object.request, object.session = handler(object.request, object.session, object.spec)
        return object
