## Analytics scalability (future)

### Current model

listening_events → direct queries → analytics endpoint

### Problem

* heavy real-time aggregation
* potential performance bottleneck at scale
* repeated query cost for popular artists

### Target architecture

listening_events → aggregates table → analytics endpoint

### Benefits

* faster queries
* reduced DB load
* enables advanced analytics features

### Status

Not implemented (MVP uses direct queries)
