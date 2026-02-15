"""Google plugin exceptions."""


class GooglePluginError(Exception):
    """Google plugin specific errors."""
    pass


class GoogleOAuthError(GooglePluginError):
    """OAuth-related errors."""
    pass
