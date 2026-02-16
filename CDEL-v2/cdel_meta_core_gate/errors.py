from __future__ import annotations


class MetaCoreGateError(Exception):
    pass


class MetaCoreGateInvalid(MetaCoreGateError):
    pass


class MetaCoreGateInternal(MetaCoreGateError):
    pass
