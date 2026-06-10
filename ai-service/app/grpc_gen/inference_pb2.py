from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'inference.proto'
)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2
from . import common_pb2 as common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x0finference.proto\x12\x11theftdetection.v1\x1a\x1fgoogle/protobuf/timestamp.proto\x1a\x0c\x63ommon.proto\"p\n\x05\x46rame\x12\x0f\n\x07payload\x18\x01 \x01(\x0c\x12\x12\n\nsession_id\x18\x02 \x01(\x03\x12\x13\n\x0b\x66rame_index\x18\x03 \x01(\x05\x12-\n\ttimestamp\x18\x04 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\"\x85\x01\n\tDetection\x12%\n\x04\x62\x62ox\x18\x01 \x01(\x0b\x32\x17.theftdetection.v1.Bbox\x12.\n\tkeypoints\x18\x02 \x03(\x0b\x32\x1b.theftdetection.v1.Keypoint\x12\r\n\x05score\x18\x03 \x01(\x02\x12\x12\n\nalert_type\x18\x04 \x01(\t2\xa2\x01\n\x10InferenceService\x12\x41\n\x07\x41nalyze\x12\x18.theftdetection.v1.Frame\x1a\x1c.theftdetection.v1.Detection\x12K\n\rAnalyzeStream\x12\x18.theftdetection.v1.Frame\x1a\x1c.theftdetection.v1.Detection(\x01\x30\x01\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'inference_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_FRAME']._serialized_start=85
  _globals['_FRAME']._serialized_end=197
  _globals['_DETECTION']._serialized_start=200
  _globals['_DETECTION']._serialized_end=333
  _globals['_INFERENCESERVICE']._serialized_start=336
  _globals['_INFERENCESERVICE']._serialized_end=498
