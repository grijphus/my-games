class PicnicError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class PicnicAuthError(PicnicError):
    pass


class Picnic2FARequired(PicnicError):
    pass


class Picnic2FAError(PicnicError):
    pass


class CheckoutError(PicnicError):
    pass
