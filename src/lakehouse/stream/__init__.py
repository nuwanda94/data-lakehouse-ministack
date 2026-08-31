"""Optional Kinesis / Firehose path into Bronze.

The batch seed path (`make seed`) remains the default producer. This
package adds a streaming-shaped producer that encodes commerce events as
Kinesis records, buffers them as a Firehose batch, and delivers one
object per event to the Bronze prefix.
"""

from lakehouse.stream.path import (
    decode_stream_payload,
    deliver_firehose_batch,
    encode_firehose_record,
    encode_kinesis_record,
    run_stream,
)

__all__ = [
    "decode_stream_payload",
    "deliver_firehose_batch",
    "encode_firehose_record",
    "encode_kinesis_record",
    "run_stream",
]
