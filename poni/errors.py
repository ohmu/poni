"""
error types

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

class Error(Exception):
    """error"""

class InvalidProperty(Error):
    """invalid property"""

class MissingProperty(Error):
    """missing property"""

class UserError(Error):
    """user error"""

class InvalidRange(Error):
    """invalid range"""

class SettingsError(Error):
    """settings error"""

class VerifyError(Error):
    """verify error"""

class TemplateError(Error):
    """template rendering error"""

class CloudError(Error):
    """cloud error"""

class RemoteError(Error):
    """remote error"""

class RemoteFileDoesNotExist(RemoteError):
    """remote file does not exist"""

class RepoError(Error):
    """repository error"""

class ImporterError(Error):
    """importer error"""

class MissingLibraryError(Error):
    """missing library error"""

class RequirementError(Error):
    """requirement error"""

class ControlError(Error):
    """control error"""

class OperationError(Error):
    """operation error"""
