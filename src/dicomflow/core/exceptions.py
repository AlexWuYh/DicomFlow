class DicomFlowError(Exception):
    """Base error with stable machine-readable code."""

    code = "INTERNAL"

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class InvalidArchiveError(DicomFlowError):
    code = "INVALID_ARCHIVE"


class ArchiveBombError(DicomFlowError):
    code = "ARCHIVE_BOMB"


class NoDicomError(DicomFlowError):
    code = "NO_DICOM"


class ConvertError(DicomFlowError):
    code = "CONVERT_ERROR"


class UploadTooLargeError(DicomFlowError):
    code = "UPLOAD_TOO_LARGE"
