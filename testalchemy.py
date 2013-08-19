# -*- coding: utf-8 -*-

import types
from sqlalchemy import event
from sqlalchemy.orm import util, Session, ScopedSession

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
        if isinstance(result, (list, tuple)):
            inst.db.add_all(result)
        else:
            inst.db.add(result)
        inst.used_properties.add(self.name)
        setattr(inst, self.name, result)
        return result

    def __call__(self, obj):
        return self.method(obj)


class Sample(object):

    class __metaclass__(type):
        def __new__(cls, cls_name, bases, attributes):
            self = type.__new__(cls, cls_name, bases, attributes)
            for name in dir(self):
                if name.startswith('_') or name == 'create_all':
                    continue
                value = getattr(self, name)
                if isinstance(value, types.MethodType):
                    new_value = value.im_func
                # already decorated attribute, assigned from another class
                elif isinstance(value, sample_property) and name!= value.name:
                    new_value = value.method
                # classmethod, staticmethod and etc
                else:
                    continue
                setattr(self, name, sample_property(new_value, name=name))
            return self

    def __init__(self, db, **kwargs):
        if isinstance(db, ScopedSession):
            db = db.registry()
        self.db = db
        self.used_properties = set()
        self.__dict__.update(kwargs)

    def create_all(self):
        if self.db.autocommit:
            self.db.begin()
        map(lambda name: getattr(self, name), dir(self))
        self.db.commit()


class Restorable(object):

    def __init__(self, db, watch=None):
        if isinstance(db, ScopedSession):
            db = db.registry()
        self.db = db
        self.watch = watch or db
        self.history = {}

    def __enter__(self):
        event.listen(self.watch, 'after_flush', self.after_flush)

    def __exit__(self, type, value, traceback):
        db = self.db
        db.rollback()
        db.expunge_all()
        old_autoflush = db.autoflush
        db.autoflush = False
        if db.autocommit:
            db.begin()
        for cls, ident_set in self.history.items():
            for ident in ident_set:
                instance = db.query(cls).get(ident)
                if instance is not None:
                    db.delete(instance)
        db.commit()
        db.close()
        db.autoflush = old_autoflush
        event.Events._remove(self.watch, 'after_flush',
                             self.after_flush)

    def after_flush(self, db, flush_context, instances=None):
        for instance in db.new:
            cls, ident = util.identity_key(instance=instance)
            self.history.setdefault(cls, set()).add(ident)


class DBHistory(object):

    def __init__(self, session):
        assert isinstance(session, (Session, ScopedSession))
        self.session = session
        #XXX: It is not clear do we need events on class or object
        self._target = session
        if isinstance(session, ScopedSession):
            self._target = session.registry()
        self.created = set()
        self.deleted = set()
        self.updated = set()
        self._created = set()
        self._deleted = set()
        self._updated = set()
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
        self.clear_cache()

    def clear_cache(self):
        self._created = set()
        self._updated = set()
        self._deleted = set()

    def __enter__(self):
        event.listen(self._target, 'after_flush', self._after_flush)
        event.listen(self._target, 'after_commit', self._after_commit)
        event.listen(self._target, 'after_soft_rollback', self._after_rollback)
        self.clear_cache()
        return self

    def __exit__(self, type, value, traceback):
        event.Events._remove(self._target, 'after_flush', self._after_flush)
        event.Events._remove(self._target, 'after_commit', self._after_commit)
        event.Events._remove(self._target, 'after_soft_rollback',
                             self._after_rollback)
        self.clear_cache()

    def _populate_idents_dict(self, idents, objects):
        for obj in objects:
            ident = util.identity_key(instance=obj)
            idents.setdefault(ident[0], set()).add(ident[1])

    def _after_flush(self, db, flush_context, instances=None):
        def identityset_to_set(obj):
            return set(obj._members.values())
        self._created = self._created.union(identityset_to_set(db.new))
        self._updated = self._updated.union(identityset_to_set(db.dirty))
        self._deleted = self._deleted.union(identityset_to_set(db.deleted))

    def _after_commit(self, db):
        if db.transaction.nested:
            #NOTE: `after_commit` is called within `_flush` for nested
            #      transactions and this is unexpected behavior
            return
        self.created = self.created.union(self._created)
        self.updated = self.updated.union(self._updated)
        self.deleted = self.deleted.union(self._deleted)
        self._populate_idents_dict(self.created_idents, self.created)
        self._populate_idents_dict(self.updated_idents, self.updated)
        self._populate_idents_dict(self.deleted_idents, self.deleted)
        self.clear_cache()

    def _after_rollback(self, db, prev_tx):
        self.clear_cache()
