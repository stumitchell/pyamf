# Copyright (c) The PyAMF Project.
# See LICENSE.txt for details.

"""
AMF Remoting support.

A Remoting request from the client consists of a short preamble, headers, and
bodies. The preamble contains basic information about the nature of the
request. Headers can be used to request debugging information, send
authentication info, tag transactions, etc. Bodies contain actual Remoting
requests and responses. A single Remoting envelope can contain several
requests; Remoting supports batching out of the box.

Client headers and bodies need not be responded to in a one-to-one manner.
That is, a body or header may not require a response. Debug information is
requested by a header but sent back as a body object. The response index is
essential for the Adobe Flash Player to understand the response therefore.

:see: `Remoting Envelope on OSFlash (external)
      <http://osflash.org/documentation/amf/envelopes/remoting>`_
:see: `Remoting Headers on OSFlash (external)
      <http://osflash.org/amf/envelopes/remoting/headers>`_
:see: `Remoting Debug Headers on OSFlash (external)
      <http://osflash.org/documentation/amf/envelopes/remoting/debuginfo>`_

:since: 0.1.0
"""

import pyamf
from pyamf import util


__all__ = ['Envelope', 'Request', 'Response', 'decode', 'encode']

#: Succesful call.
STATUS_OK = 0
#: Reserved for runtime errors.
STATUS_ERROR = 1
#: Debug information.
STATUS_DEBUG = 2

#: List of available status response codes.
STATUS_CODES = {
    STATUS_OK:    '/onResult',
    STATUS_ERROR: '/onStatus',
    STATUS_DEBUG: '/onDebugEvents'
}

#: AMF mimetype.
CONTENT_TYPE = 'application/x-amf'

ERROR_CALL_FAILED, = range(1)
ERROR_CODES = {
    ERROR_CALL_FAILED: 'Server.Call.Failed'
}

APPEND_TO_GATEWAY_URL = 'AppendToGatewayUrl'
REPLACE_GATEWAY_URL = 'ReplaceGatewayUrl'
REQUEST_PERSISTENT_HEADER = 'RequestPersistentHeader'


class RemotingError(pyamf.BaseError):
    """
    Generic remoting error class.
    """


class RemotingCallFailed(RemotingError):
    """
    Raised if `Server.Call.Failed` received.
    """

pyamf.add_error_class(RemotingCallFailed, ERROR_CODES[ERROR_CALL_FAILED])


class HeaderCollection(dict):
    """
    Collection of AMF message headers.
    """

    def __init__(self, raw_headers={}):
        self.required = []

        for (k, ig, v) in raw_headers:
            self[k] = v
            if ig:
                self.required.append(k)

    def is_required(self, idx):
        """
        :raise KeyError: Unknown header found.
        """
        if not idx in self:
            raise KeyError("Unknown header %s" % str(idx))

        return idx in self.required

    def set_required(self, idx, value=True):
        """
        :raise KeyError: Unknown header found.
        """
        if not idx in self:
            raise KeyError("Unknown header %s" % str(idx))

        if not idx in self.required:
            self.required.append(idx)

    def __len__(self):
        return len(self.keys())


class Envelope(object):
    """
    I wrap an entire request, encapsulating headers and bodies.

    There can be more than one request in a single transaction.

    :ivar amfVersion: AMF encoding version. See :class:`pyamf.ENCODING_TYPES`
    :type amfVersion: `int` or `None`
    :ivar headers: AMF headers, a list of name, value pairs. Global to each
        request.
    :type headers: :class:`HeaderCollection`
    :ivar bodies: A list of requests/response messages
    :type bodies: `list` containing tuples of the key of the request and
        the instance of the :class:`Message`
    """

    def __init__(self, amfVersion=None):
        self.amfVersion = amfVersion
        self.headers = HeaderCollection()
        self.bodies = []

    def __repr__(self):
        r = "<Envelope amfVersion=%r>\n" % (self.amfVersion,)

        for h in self.headers:
            r += " " + repr(h) + "\n"

        for request in iter(self):
            r += " " + repr(request) + "\n"

        r += "</Envelope>"

        return r

    def __setitem__(self, name, value):
        if not isinstance(value, Message):
            raise TypeError("Message instance expected")

        idx = 0
        found = False

        for body in self.bodies:
            if name == body[0]:
                self.bodies[idx] = (name, value)
                found = True

            idx = idx + 1

        if not found:
            self.bodies.append((name, value))

        value.envelope = self

    def __getitem__(self, name):
        for body in self.bodies:
            if name == body[0]:
                return body[1]

        raise KeyError("'%r'" % (name,))

    def __nonzero__(self):
        return len(self.bodies) != 0 or len(self.headers) != 0

    def __iter__(self):
        for body in self.bodies:
            yield body[0], body[1]

        raise StopIteration

    def __len__(self):
        return len(self.bodies)

    def iteritems(self):
        for body in self.bodies:
            yield body

        raise StopIteration

    def keys(self):
        return [body[0] for body in self.bodies]

    def items(self):
        return self.bodies

    def __contains__(self, name):
        for body in self.bodies:
            if name == body[0]:
                return True

        return False

    def __eq__(self, other):
        if isinstance(other, Envelope):
            return (self.amfVersion == other.amfVersion and
                self.headers == other.headers and
                self.bodies == other.bodies)

        if hasattr(other, 'keys') and hasattr(other, 'items'):
            keys, o_keys = self.keys(), other.keys()

            if len(o_keys) != len(keys):
                return False

            for k in o_keys:
                if k not in keys:
                    return False

                keys.remove(k)

            for k, v in other.items():
                if self[k] != v:
                    return False

            return True


class Message(object):
    """
    I represent a singular request/response, containing a collection of
    headers and one body of data.

    I am used to iterate over all requests in the :class:`Envelope`.

    :ivar envelope: The parent envelope of this AMF Message.
    :type envelope: :class:`Envelope`
    :ivar body: The body of the message.
    :type body: `mixed`
    :ivar headers: The message headers.
    :type headers: `dict`
    """

    def __init__(self, envelope, body):
        self.envelope = envelope
        self.body = body

    def _get_headers(self):
        return self.envelope.headers

    headers = property(_get_headers)


class Request(Message):
    """
    An AMF Request payload.

    :ivar target: The target of the request
    :type target: `basestring`
    """

    def __init__(self, target, body=[], envelope=None):
        Message.__init__(self, envelope, body)

        self.target = target

    def __repr__(self):
        return "<%s target=%s>%s</%s>" % (
            type(self).__name__, repr(self.target), repr(self.body), type(self).__name__)


class Response(Message):
    """
    An AMF Response.

    :ivar status: The status of the message. Default is :const:`STATUS_OK`.
    :type status: Member of :data:`STATUS_CODES`.
    """

    def __init__(self, body, status=STATUS_OK, envelope=None):
        Message.__init__(self, envelope, body)

        self.status = status

    def __repr__(self):
        return "<%s status=%s>%s</%s>" % (
            type(self).__name__, _get_status(self.status), repr(self.body),
            type(self).__name__
        )


class BaseFault(object):
    """
    I represent a `Fault` message (`mx.rpc.Fault`).

    :ivar level: The level of the fault.
    :type level: `str`
    :ivar code: A simple code describing the fault.
    :type code: `str`
    :ivar details: Any extra details of the fault.
    :type details: `str`
    :ivar description: Text description of the fault.
    :type description: `str`

    :see: `mx.rpc.Fault on Livedocs (external)
          <http://livedocs.adobe.com/flex/201/langref/mx/rpc/Fault.html>`
    """

    level = None

    class __amf__:
        static = ('level', 'code', 'type', 'details', 'description')

    def __init__(self, *args, **kwargs):
        self.code = kwargs.get('code', '')
        self.type = kwargs.get('type', '')
        self.details = kwargs.get('details', '')
        self.description = kwargs.get('description', '')

    def __repr__(self):
        x = '%s level=%s' % (self.__class__.__name__, self.level)

        if self.code not in ('', None):
            x += ' code=%s' % repr(self.code)
        if self.type not in ('', None):
            x += ' type=%s' % repr(self.type)
        if self.description not in ('', None):
            x += ' description=%s' % repr(self.description)

        if self.details not in ('', None):
            x += '\nTraceback:\n%s' % (repr(self.details),)

        return x

    def raiseException(self):
        """
        Raises an exception based on the fault object. There is no traceback
        available.
        """
        raise get_exception_from_fault(self), self.description, None


class ErrorFault(BaseFault):
    """
    I represent an error level fault.
    """

    level = 'error'


def _read_header(stream, decoder, strict=False):
    """
    Read AMF L{Message} header.

    :type   stream: :class:`BufferedByteStream<pyamf.util.BufferedByteStream>`
    :param  stream: AMF data.
    :type   decoder: :class:`amf0.Decoder<pyamf.amf0.Decoder>`
    :param  decoder: AMF decoder instance
    :type strict: `bool`
    :param strict: Use strict decoding policy. Default is C{False}.
    :raise DecodeError: The data that was read from the stream
    does not match the header length.

    :rtype: C{tuple}
    :return:
     - Name of the header.
     - A C{bool} determining if understanding this header is
     required.
     - Value of the header.
    """
    name_len = stream.read_ushort()
    name = stream.read_utf8_string(name_len)

    required = bool(stream.read_uchar())

    data_len = stream.read_ulong()
    pos = stream.tell()

    data = decoder.readElement()

    if strict and pos + data_len != stream.tell():
        raise pyamf.DecodeError(
            "Data read from stream does not match header length")

    return (name, required, data)


def _write_header(name, header, required, stream, encoder, strict=False):
    """
    Write AMF message header.

    :type   name: `str`
    :param  name: Name of the header.
    :type   header:
    :param  header: Raw header data.
    :type   required: `bool`
    :param  required: Required header.
    :type   stream: :class:`BufferedByteStream<pyamf.util.BufferedByteStream>`
    :param  stream: AMF data.
    :type   encoder: :class:`amf0.Encoder<pyamf.amf0.Encoder>` or
                     :class:`amf3.Encoder<pyamf.amf3.Encoder>`
    :param  encoder: AMF encoder instance.
    :type strict: `bool`
    :param strict: Use strict encoding policy. Default is `False`.
    """
    stream.write_ushort(len(name))
    stream.write_utf8_string(name)

    stream.write_uchar(required)
    write_pos = stream.tell()

    stream.write_ulong(0)
    old_pos = stream.tell()
    encoder.writeElement(header)
    new_pos = stream.tell()

    if strict:
        stream.seek(write_pos)
        stream.write_ulong(new_pos - old_pos)
        stream.seek(new_pos)


def _read_body(stream, decoder, strict=False, logger=None):
    """
    Read AMF message body.

    :param stream: AMF data.
    :type stream: :class:`BufferedByteStream<pyamf.util.BufferedByteStream>`
    :param decoder: AMF decoder instance.
    :type decoder: :class:`amf0.Decoder<pyamf.amf0.Decoder>`
    :param strict: Use strict decoding policy. Default is `False`.
    :type strict: `bool`
    :raise DecodeError: Data read from stream does not match body length.
    :param logger: Used to log interesting events whilst reading a remoting
        body.
    :type logger: A `logging.Logger` instance or `None`.

    :rtype: `tuple`
    :return: A `tuple` containing:
        - ID of the request
        - :class:`Request` or :class:`Response`
    """
    def _read_args():
        """
        :raise pyamf.DecodeError: Array type required for request body.
        """
        # we have to go through this insanity because it seems that amf0
        # does not keep the array of args in the object references lookup
        type_byte = stream.peek(1)

        if type_byte == '\x11':
            if not decoder.use_amf3:
                raise pyamf.DecodeError(
                    "Unexpected AMF3 type with incorrect message type")

            return decoder.readElement()

        if type_byte != '\x0a':
            raise pyamf.DecodeError("Array type required for request body")

        stream.read(1)
        x = stream.read_ulong()

        return [decoder.readElement() for i in xrange(x)]

    target = stream.read_utf8_string(stream.read_ushort())
    response = stream.read_utf8_string(stream.read_ushort())

    status = STATUS_OK
    is_request = True

    for code, s in STATUS_CODES.iteritems():
        if not target.endswith(s):
            continue

        is_request = False
        status = code
        target = target[:0 - len(s)]

    if logger:
        logger.debug('Remoting target: %r' % (target,))

    data_len = stream.read_ulong()
    pos = stream.tell()

    if is_request:
        data = _read_args()
    else:
        data = decoder.readElement()

    if strict and pos + data_len != stream.tell():
        raise pyamf.DecodeError("Data read from stream does not match body "
            "length (%d != %d)" % (pos + data_len, stream.tell(),))

    if is_request:
        return response, Request(target, body=data)

    if status == STATUS_ERROR and isinstance(data, pyamf.ASObject):
        data = get_fault(data)

    return target, Response(data, status)


def _write_body(name, message, stream, encoder, strict=False):
    """
    Write AMF message body.

    :param name: The name of the request.
    :type name: `basestring`
    :param message: The AMF payload.
    :type message: :class:`Request` or :class:`Response`
    :type stream: :class:`BufferedByteStream<pyamf.util.BufferedByteStream>`
    :type encoder: :class:`amf0.Encoder<pyamf.amf0.Encoder>`
    :param encoder: Encoder to use.
    :type strict: `bool`
    :param strict: Use strict encoding policy. Default is `False`.

    :raise TypeError: Unknown message type for `message`.
    """
    def _encode_body(message):
        if isinstance(message, Response):
            encoder.writeElement(message.body)

            return

        stream.write('\x0a')
        stream.write_ulong(len(message.body))
        for x in message.body:
            encoder.writeElement(x)

    if not isinstance(message, (Request, Response)):
        raise TypeError("Unknown message type")

    target = None

    if isinstance(message, Request):
        target = unicode(message.target)
    else:
        target = u"%s%s" % (name, _get_status(message.status))

    target = target.encode('utf8')

    stream.write_ushort(len(target))
    stream.write_utf8_string(target)

    response = 'null'

    if isinstance(message, Request):
        response = name

    stream.write_ushort(len(response))
    stream.write_utf8_string(response)

    if not strict:
        stream.write_ulong(0)
        _encode_body(message)

        return

    write_pos = stream.tell()
    stream.write_ulong(0)
    old_pos = stream.tell()

    _encode_body(message)
    new_pos = stream.tell()

    stream.seek(write_pos)
    stream.write_ulong(new_pos - old_pos)
    stream.seek(new_pos)


def _get_status(status):
    """
    Get status code.

    :type status: `str`
    :raise ValueError: The status code is unknown.
    :return: Status code.
    :see: :list:`STATUS_CODES`
    """
    if status not in STATUS_CODES.keys():
        # TODO print that status code..
        raise ValueError("Unknown status code")

    return STATUS_CODES[status]


def get_fault_class(level, **kwargs):
    if level == 'error':
        return ErrorFault

    return BaseFault


def get_fault(data):
    try:
        level = data['level']
        del data['level']
    except KeyError:
        level = 'error'

    e = {}

    for x, y in data.iteritems():
        if isinstance(x, unicode):
            e[str(x)] = y
        else:
            e[x] = y

    return get_fault_class(level, **e)(**e)


def decode(stream, context=None, strict=False, logger=None, timezone_offset=None):
    """
    Decodes the incoming stream as a remoting message.

    :param stream: AMF data.
    :type stream: :class:`BufferedByteStream<pyamf.util.BufferedByteStream>`
    :param context: Context.
    :type context: :class:`amf0.Context<pyamf.amf0.Context>` or
                   :class:`amf3.Context<pyamf.amf3.Context>`
    :param strict: Enforce strict decoding. Default is `False`.
    :type strict: `bool`
    :param logger: Used to log interesting events whilst decoding a remoting
        message.
    :type logger: A `logging.Logger` instance or `None`.
    :param timezone_offset: The difference between the current timezone and
        UTC. Date/times should always be handled in UTC to avoid confusion but
        this is required for legacy systems.
    :type timezone_offset: `datetime.timedelta`

    :raise DecodeError: Malformed stream.
    :raise RuntimeError: Decoder is unable to fully consume the
        stream buffer.

    :return: Message envelope.
    :rtype: :class:`Envelope`
    """
    if not isinstance(stream, util.BufferedByteStream):
        stream = util.BufferedByteStream(stream)

    if logger is not None:
        logger.debug('remoting.decode start')

    msg = Envelope()
    msg.amfVersion = stream.read_ushort()

    # see http://osflash.org/documentation/amf/envelopes/remoting#preamble
    # why we are doing this...
    if msg.amfVersion > 0x09:
        raise pyamf.DecodeError("Malformed stream (amfVersion=%d)" %
            msg.amfVersion)

    if context is None:
        context = pyamf.get_context(pyamf.AMF0)

    context.clear()

    decoder = pyamf.get_decoder(pyamf.AMF0, stream, context=context,
        strict=strict, timezone_offset=timezone_offset)

    decoder.use_amf3 = msg.amfVersion == pyamf.AMF3

    header_count = stream.read_ushort()

    for i in xrange(header_count):
        name, required, data = _read_header(stream, decoder, strict)
        msg.headers[name] = data

        if required:
            msg.headers.set_required(name)

    body_count = stream.read_short()

    for i in range(body_count):
        context.clear()

        target, payload = _read_body(stream, decoder, strict, logger)
        msg[target] = payload

    if strict and stream.remaining() > 0:
        raise RuntimeError("Unable to fully consume the buffer")

    if logger is not None:
        logger.debug('remoting.decode end')

    return msg


def encode(msg, context=None, strict=False, logger=None, timezone_offset=None):
    """
    Encodes AMF stream and returns file object.

    :type   msg: :class:`Envelope`
    :param  msg: The message to encode.
    :type strict: `bool`
    :param strict: Determines whether encoding should be strict. Specifically
        header/body lengths will be written correctly, instead of the default 0.
        Default is `False`. Introduced in 0.4.
    :param logger: Used to log interesting events whilst encoding a remoting
        message.
    :type logger: A `logging.Logger` instance or `None`.
    :param timezone_offset: The difference between the current timezone and
        UTC. Date/times should always be handled in UTC to avoid confusion but
        this is required for legacy systems.
    :type timezone_offset: `datetime.timedelta`
    :rtype: `StringIO`
    :return: File object.
    """
    stream = util.BufferedByteStream()

    if context is None:
        context = pyamf.get_context(pyamf.AMF0)

    encoder = pyamf.get_encoder(pyamf.AMF0, stream, context=context,
        timezone_offset=timezone_offset, strict=strict)

    if msg.amfVersion == pyamf.AMF3:
        encoder.use_amf3 = True

    stream.write_ushort(msg.amfVersion)
    stream.write_ushort(len(msg.headers))

    for name, header in msg.headers.iteritems():
        _write_header(
            name, header, int(msg.headers.is_required(name)),
            stream, encoder, strict)

    stream.write_short(len(msg))

    for name, message in msg.iteritems():
        encoder.context.clear()

        _write_body(name, message, stream, encoder, strict)

    stream.seek(0)

    return stream


def get_exception_from_fault(fault):
    """
    :raise RemotingError: Default exception from fault.
    """
    # XXX nick: threading problems here?
    try:
        return pyamf.ERROR_CLASS_MAP[fault.code]
    except KeyError:
        # default to RemotingError
        return RemotingError


pyamf.register_class(ErrorFault)
