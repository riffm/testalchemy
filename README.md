testalchemy
===========

testalchemy - A set of utility classes for testing code that uses sqlalchemy


##Installation

```
   $ git clone git://github.com/riffm/testalchemy.git
   $ cd testalchemy
   $ [sudo] python setup.py install
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
...     print session.query(User).all() 
...
...
[<__main__.User object at 0x10d489fd0>] 
>>> print session.query(User).all()
[]
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
...     assert history.last_created(User) == set([user])
...
...
```
