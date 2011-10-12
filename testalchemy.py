# -*- coding: utf-8 -*-

import types
from sqlalchemy import event
from sqlalchemy.orm import util, Session

__all__ = ['Sample', 'Restorable', 'DBHistory']


class sample_property(object):
    def __init__(self, method, name=None):
        self.method = method
        self.__doc__ = method.__doc__
        self.name = name or method.__name__

    def __get__(self, inst, cls):
        if inst is None:
            return self
        result = self.method(inst)
        inst.db.add(result)
        inst.used_properties.add(self.name)
        setattr(inst, self.name, result)
        return result


class Sample(object):
    class __metaclass__(type):
        def __new__(cls, cls_name, bases, attributes):
            attributes['_decorated_methods'] = decorated_methods = {}
            attrs_list = [attributes]
            for base in bases:
                if hasattr(base, '_decorated_methods'):
                    decorated_methods.update(base._decorated_methods)
                else:
                    attrs_list.insert(0, base.__dict__)
            for attrs in attrs_list:
                for attr_name, attr_value in attrs.items():
                    if attr_name.startswith('_') or attr_name=='create_all':
                        continue
                    if isinstance(attr_value, types.FunctionType):
                        decorated_methods[attr_name] = attr_value
                        attributes[attr_name] = sample_property(attr_value)
                    elif isinstance(attr_value, sample_property):
                        new_value = sample_property(attr_value.method,
                                                    name=attr_name)
                        decorated_methods[attr_name] = attr_value.method
                        attributes[attr_name] = new_value
            return type.__new__(cls, cls_name, bases, attributes)

    def __init__(self, db, **kwargs):
        self.db = db
        self.used_properties = set()
        self.__dict__.update(kwargs)

    def create_all(self):
        for attr_name in self._decorated_methods.keys():
            getattr(self, attr_name)
        self.db.commit()


class Restorable(object):
    def __init__(self, db, event_target=None):
        self.db = db
        self.event_target = event_target or db
        self.history = {}

    def __enter__(self):
        event.listen(self.event_target, 'after_flush', self.after_flush)

    def __exit__(self, type, value, traceback):
        db = self.db
        db.rollback()
        db.expunge_all()
        old_autoflush = db.autoflush
        db.autoflush = False
        for cls, ident_set in self.history.items():
            for ident in ident_set:
                instance = db.query(cls).get(ident)
                if instance is not None:
                    db.delete(instance)
        db.commit()
        db.close()
        db.autoflush = old_autoflush
        event.Events._remove(self.event_target, 'after_flush',
                             self.after_flush)

    def after_flush(self, db, flush_context, instances=None):
        for instance in db.new:
            cls, ident = util.identity_key(instance=instance)
            self.history.setdefault(cls, set()).add(ident)


class DBHistory(object):

    def __init__(self, session):
        assert isinstance(session, Session)
        self.session = session
        self.created = set()
        self.deleted = set()
        self.updated = set()
        self.created_idents = {}
        self.updated_idents = {}
        self.deleted_idents = {}

    def last(self, model_cls, mode):
        assert mode in ('created', 'updated', 'deleted')
        if mode == 'deleted':
            # Because there is not data in DB we return detached object set.
            return set([inst for inst in self.deleted \
                        if isinstance(inst, model_cls)])
        idents = getattr(self, '%s_idents' % mode).get(model_cls, set())
        return set([self.session.query(model_cls).get(ident) \
                    for ident in idents])

    def last_created(self, model_cls):
        return self.last(model_cls, 'created')

    def last_updated(self, model_cls):
        return self.last(model_cls, 'updated')

    def last_deleted(self, model_cls):
        return self.last(model_cls, 'deleted')

    def assert_(self, model_cls, ident=None, mode='created'):
        dataset = self.last(model_cls, mode)
        error_msg = 'No instances of %s were %s' % (model_cls, mode)
        assert dataset, error_msg
        if ident is not None:
            ident = ident if isinstance(ident, (tuple, list)) else (ident,)
            item = [i for i in dataset \
                    if util.identity_key(instance=i)[1] == ident]
            assert item,'No insatances of %s with identity %r were %s' % \
                   (model_cls, ident, mode)
            return item[0]
        return dataset

    def assert_created(self, model_cls, ident=None):
        return self.assert_(model_cls, ident, 'created')

    def assert_updated(self, model_cls, ident=None):
        return self.assert_(model_cls, ident, 'updated')

    def assert_deleted(self, model_cls, ident=None):
        return self.assert_(model_cls, ident, 'deleted')

    def assert_one(self, dataset, model_cls, mode):
        if len(dataset) != 1:
            raise AssertionError('%d instance(s) of %s %s, '
                                 'need only one' % (len(dataset),
                                                    model_cls,
                                                    mode))
        return dataset.pop()

    def assert_created_one(self, model_cls):
        result = self.assert_created(model_cls)
        return self.assert_one(result, model_cls, 'created')

    def assert_deleted_one(self, model_cls):
        result = self.assert_deleted(model_cls)
        return self.assert_one(result, model_cls, 'deleted')

    def assert_updated_one(self, model_cls):
        result = self.assert_updated(model_cls)
        return self.assert_one(result, model_cls, 'updated')

    def clear(self):
        self.created = set()
        self.deleted = set()
        self.updated = set()
        self.created_idents = {}
        self.updated_idents = {}
        self.deleted_idents = {}

    def __enter__(self):
        event.listen(self.session.__class__, 'after_flush', self._after_flush)
        return self

    def __exit__(self, type, value, traceback):
        event.Events._remove(self.session.__class__, 'after_flush',
                             self._after_flush)

    def _populate_idents_dict(self, idents, objects):
        for obj in objects:
            ident = util.identity_key(instance=obj)
            idents.setdefault(ident[0], set()).add(ident[1])

    def _after_flush(self, db, flush_context, instances=None):
        def identityset_to_set(obj):
            return set(obj._members.values())
        self.created = self.created.union(identityset_to_set(db.new))
        self.updated = self.updated.union(identityset_to_set(db.dirty))
        self.deleted = self.deleted.union(identityset_to_set(db.deleted))
        self._populate_idents_dict(self.created_idents, self.created)
        self._populate_idents_dict(self.updated_idents, self.updated)
        self._populate_idents_dict(self.deleted_idents, self.deleted)
