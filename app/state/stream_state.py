from app.services.stream_pipeline import StreamPipeline

_pipeline: StreamPipeline | None = None


def get_stream_pipeline() -> StreamPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = StreamPipeline()
    return _pipeline
