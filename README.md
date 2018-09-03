`automessage` is a library that helps you quickly create `protorpc`-based web services that interact
with `ndb` models (Google Cloud Datastore) by automatically generating `Message` classes for your
`ndb.Model` subclasses, along with easy serialization/deserialization.

## Caveats

* This is pretty rough, alpha-level code. There are lots of TODOs. Use at your own risk.
* This only works for Google App Engine standard environment + Python with the `protorpc` and `ndb`
  libraries.

## Installation

[Follow this guide](https://cloud.google.com/appengine/docs/standard/python/tools/using-libraries-python-27)
to install automessage as a third-party library for your App Engine Python app; the `pip` command
you want is:

    pip install -t lib/ automessage

## Usage

First, use a `@automessage.attach` decorator on your `ndb.Model` subclass:

```python
from google.appengine.ext import ndb
import automessage

@automessage.attach()
class Book(ndb.Model):
  title = ndb.StringProperty()
  author = ndb.StringProperty()
  publish_date = ndb.DateTimeProperty(indexed=True)
```

This generates a class `BookMessage` (a subclass of `protorpc.messages.Message`) in the same module
as the `Book` class, that you can then use in your `protorpc`-based services, like so:

```python
class BooksService(remote.Service):
  class FindRequest(messages.Message):
    title = messages.StringField(1, required=True)

  @remote.method(FindRequest, BookMessage)
  def find(self, request):
    return (Book
        .query(Book.title == request.title)
        .to_message()) # to_message() added by automessage

  @remote.method(BookMessage, BookMessage)
  def create(self, request):
    book = Book.from_message(request) # from_message() added by automessage
    book.put()
    return book.to_message()
```

`attach` takes several parameters (see the code for details) that lets you customize the name of the
generated message class, convert to camel case, add an ID field, blacklist/whitelist properties,
etc. You can decorate models with multiple `attach` calls (with different parameters) to create
multiple message types for a given model. When doing so, you'll need to provide the message type
in `to_message` calls, e.g. `book.to_message(CustomBookMessage)`.

## Related work

* [Protopigeon](https://github.com/theacodes/Protopigeon) is an almost identical, older approach with a slightly different API and better testing.
