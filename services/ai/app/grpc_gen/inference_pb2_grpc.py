import grpc
import warnings

from . import inference_pb2 as inference__pb2

GRPC_GENERATED_VERSION = '1.71.2'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in inference_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class InferenceServiceStub(object):

    def __init__(self, channel):
        self.Analyze = channel.unary_unary(
                '/theftdetection.v1.InferenceService/Analyze',
                request_serializer=inference__pb2.Frame.SerializeToString,
                response_deserializer=inference__pb2.Detection.FromString,
                _registered_method=True)
        self.AnalyzeStream = channel.stream_stream(
                '/theftdetection.v1.InferenceService/AnalyzeStream',
                request_serializer=inference__pb2.Frame.SerializeToString,
                response_deserializer=inference__pb2.Detection.FromString,
                _registered_method=True)


class InferenceServiceServicer(object):

    def Analyze(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def AnalyzeStream(self, request_iterator, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_InferenceServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'Analyze': grpc.unary_unary_rpc_method_handler(
                    servicer.Analyze,
                    request_deserializer=inference__pb2.Frame.FromString,
                    response_serializer=inference__pb2.Detection.SerializeToString,
            ),
            'AnalyzeStream': grpc.stream_stream_rpc_method_handler(
                    servicer.AnalyzeStream,
                    request_deserializer=inference__pb2.Frame.FromString,
                    response_serializer=inference__pb2.Detection.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'theftdetection.v1.InferenceService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('theftdetection.v1.InferenceService', rpc_method_handlers)


class InferenceService(object):

    @staticmethod
    def Analyze(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/theftdetection.v1.InferenceService/Analyze',
            inference__pb2.Frame.SerializeToString,
            inference__pb2.Detection.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def AnalyzeStream(request_iterator,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.stream_stream(
            request_iterator,
            target,
            '/theftdetection.v1.InferenceService/AnalyzeStream',
            inference__pb2.Frame.SerializeToString,
            inference__pb2.Detection.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
