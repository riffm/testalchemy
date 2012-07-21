testalchemy
===========

testalchemy - A set of utility classes for testing code that uses sqlalchemy


##Installation

```
   $ git clone git://github.com/riffm/testalchemy.git
   $ cd testalchemy
   $ python setup.py install
```


##Support
Python 2.6+


##Development

Run tests

```
    $ python setup.py test

    # or with tox
    $ tox
```


##Example of use
###testalchemy.Restorable

```
>>> with Restorable(session):
...     user = User(name='john')
...     session.add(user)
...     session.commit()
...     print session.query(User).all() <-,
...                                       |
...                                       |
[<__main__.User object at 0x10d489fd0>] # patched session
>>> print session.query(User).all()
[]  # original session
```

###testalchemy.Sample

```
>>> class DataSample(Sample):
...    def john(self):
...        return User(name='John')
...    
...    def john_family(self):
...        family = [User(name="Smith"),
...                  User(name="Helga")]
...        return family
...
...
>>> sample = DataSample(session)
>>> print session.query(User).all()
[]
>>>
>>> sample.create_all() # create all objects from DataSample
>>>
>>> print session.query(User).all()
[<__main__.User object at 0x10d489e90>, <__main__.User object at 0x10d489e91>, <__main__.User object at 0x10d489e92>]
```

###testalchemy.DBHistory

```
>>> with DBHistory(session) as history:
...     user = User(name='test')
...     session.add(user)
...     session.commit()
...     print history.__dict__
...
...
{
 'updated': set([]),
 'created': set([<__main__.User object at 0x10d4964d0>]),
 'deleted': set([]),
 '_target': <sqlalchemy.orm.session.SessionMaker object at 0x10ca9bc90>,
 'created_idents': {<class '__main__.User'>: set([(2,)])},
 'session': <sqlalchemy.orm.session.SessionMaker object at 0x10ca9bc90>,
 'deleted_idents': {},
 'updated_idents': {}
}
```
