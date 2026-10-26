class BlurbItException(Exception):

    """Base exception for this library."""


class InstallationNotFound(BlurbItException):

    """App not installed by user."""


class GitHubUnavailable(BlurbItException):

    """GitHub could not be reached or did not answer properly.

    Raised when GitHub is down, rate limiting, or serving an HTML
    interstitial page instead of the API response we asked for.
    """


class SignInFailed(BlurbItException):

    """GitHub rejected the OAuth sign-in, for example an expired code."""


class OAuthMisconfigured(BlurbItException):

    """GitHub rejected our OAuth app credentials or callback URL.

    Only a deploy can fix this, so it is left to surface as a 500 that
    Sentry reports rather than being shown to the user as their mistake.
    """
