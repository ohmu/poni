"""
error types

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

class Error(Exception):
    """error"""

class InvalidProperty(Error):
    """invalid property"""

class UserError(Error):
    """user error"""

class InvalidRange(Error):
    """invalid range"""

class SettingsError(Error):
    """settings error"""

class VerifyError(Error):
    """verify error"""

class CloudError(Error):
    """cloud error"""

class RemoteError(Error):
    """remote error"""

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
