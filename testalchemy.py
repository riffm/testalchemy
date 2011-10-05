# -*- coding: utf-8 -*-

import types
from sqlalchemy import event
from sqlalchemy.orm import util

__all__ = ['Sample', 'Restorable', 'ModelsHistory']


class sample_property(object):
    def __init__(self, method):
        self.method = method
        self.__doc__ = method.__doc__

    def __get__(self, inst, cls):
        if inst is None:
            return self
        result = self.method(inst)
        inst.db.add(result)
        method_name = self.method.__name__
        inst.used_properties.add(method_name)
        setattr(inst, method_name, result)
        return result


class SampleMeta(type):
    def __new__(cls, cls_name, bases, namespace):
        namespace['_decorated_methods'] = decorated_methods = {}
        for attr_name, attr_value in namespace.items():
            if not (attr_name.startswith('_') or attr_name == 'create_all') \
            and isinstance(attr_value, (types.FunctionType, types.LambdaType)):
                decorated_methods[attr_name] = attr_value
                namespace[attr_name] = sample_property(attr_value)
        return type.__new__(cls, cls_name, bases, namespace)


class Sample(object):
    __metaclass__ = SampleMeta

    def __init__(self, db):
        self.db = db
        self.used_properties = set()

    def create_all(self):
        for attr_name, attr_value in self.__class__.__dict__.items():
            if isinstance(attr_value, sample_property):
                getattr(self, attr_name)
        self.db.commit()


class Restorable(object):
    def __init__(self, session_maker):
        self.session_maker = session_maker
        self.history = {}
        self.db = None

    def __enter__(self):
        event.listen(self.session_maker, 'after_flush', self.after_flush)
        self.db = self.session_maker()
        return self.db

    def __exit__(self, type, value, traceback):
        self.db.close()
        db = self.session_maker()
        db.autoflush = False
        for cls, ident_set in self.history.items():
            for ident in ident_set:
                instance = db.query(cls).get(ident)
                if instance is not None:
                    db.delete(instance)
        db.commit()
        db.close()
        event.Events._remove(self.session_maker, 'after_flush', self.after_flush)

    def after_flush(self, db, flush_context, instances=None):
        for instance in db.new:
            cls, ident = util.identity_key(instance=instance)
            self.history.setdefault(cls, set()).add(ident)


class ModelsHistory(object):

    def __init__(self, db):
        self.db = db
        self.created = set()
        self.deleted = set()
        self.updated = set()

    def last(self, model_cls, mode):
        assert mode in ('created', 'updated', 'deleted')
        dataset = getattr(self, mode)
        return set([item for item in dataset if isinstance(item, model_cls)])

    def last_created(self, model_cls):
        return self.last(model_cls, 'created')

    def last_updated(self, model_cls):
        return self.last(model_cls, 'updated')

    def last_deleted(self, model_cls):
        return self.last(model_cls, 'deleted')

    def assert_(self, model_cls, ident=None, mode='created'):
        dataset = self.last(model_cls, mode)
        error_msg = 'No insatances of %s were %s' % (model_cls, mode)
        assert dataset, error_msg
        if ident is not None:
            ident = ident if isinstance(ident, (tuple, list)) else (ident,)
            item = [i for i in dataset \
                    if util.identity_key(instance=i)[1] == ident]
            assert item,'No insatances of %s with %r were %s' % (model_cls,
                                                                 ident,
                                                                 mode)
            return item[0]
        return dataset

    def assert_created(self, model_cls, ident=None):
        return self.assert_(model_cls, ident, 'created')

    def assert_updated(self, model_cls, ident=None):
        return self.assert_(model_cls, ident, 'updated')

    def assert_deleted(self, model_cls, ident=None):
        return self.assert_(model_cls, ident, 'deleted')

    def clear(self):
        self.created = set()
        self.deleted = set()
        self.updated = set()

    def __enter__(self):
        event.listen(self.db, 'after_flush', self._after_flush)
        return self

    def __exit__(self, type, value, traceback):
        self.clear()
        event.Events._remove(self.db, 'after_flush', self._after_flush)

    def _after_flush(self, db, flush_context, instances=None):
        def identityset_to_set(obj):
            return set(obj._members.values())
        self.created = self.created.union(identityset_to_set(db.new))
        self.updated = self.updated.union(identityset_to_set(db.dirty))
        self.deleted = self.deleted.union(identityset_to_set(db.deleted))
