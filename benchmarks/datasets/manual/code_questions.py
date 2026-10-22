"""Вопросы домена `code` по исходникам и документации httpx 0.28.1 и click 8.1.8."""

from benchmarks.datasets.manual import Entry

HX = 'code/httpx/'
CL = 'code/click/'

CODE: list[Entry] = [
    # --- httpx: исходный код ---
    (
        'code-httpx-default-timeout',
        'What is the default timeout used by httpx clients and where is it defined?',
        'Five seconds for all operations: `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)` in '
        'httpx/_config.py.',
        [HX + 'httpx/_config.py', HX + 'docs/quickstart.md'],
        ['DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)'],
    ),
    (
        'code-httpx-default-limits',
        'What are the default connection pool limits in httpx?',
        'max_connections=100, max_keepalive_connections=20, and keepalive_expiry of 5 seconds '
        '(`DEFAULT_LIMITS` in httpx/_config.py).',
        [HX + 'httpx/_config.py', HX + 'docs/advanced/resource-limits.md'],
        [
            'DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20)',
            'keepalive_expiry: float | None = 5.0',
        ],
    ),
    (
        'code-httpx-max-redirects',
        'How many redirects will an httpx client follow before giving up, and which exception '
        'is raised?',
        '20 by default (`DEFAULT_MAX_REDIRECTS = 20`); when exceeded, `_send_handling_redirects` '
        'raises `TooManyRedirects("Exceeded maximum allowed redirects.")`.',
        [HX + 'httpx/_config.py', HX + 'httpx/_client.py'],
        [
            'DEFAULT_MAX_REDIRECTS = 20',
            'raise TooManyRedirects( "Exceeded maximum allowed redirects.", request=request',
        ],
    ),
    (
        'code-httpx-follow-redirects-default',
        'Does httpx.Client follow redirects by default? How is this different from requests?',
        'No. `follow_redirects` defaults to False; unlike requests, HTTPX does not follow '
        'redirects by default, you must pass `follow_redirects=True` per request or on the '
        'client.',
        [HX + 'httpx/_client.py', HX + 'docs/compatibility.md'],
        [
            'Unlike `requests`, HTTPX does **not follow redirects by default**.',
            'client = httpx.Client(follow_redirects=True)',
        ],
    ),
    (
        'code-httpx-raise-for-status',
        'What does Response.raise_for_status() do for a 2xx response and for an error, and '
        'when does it raise RuntimeError?',
        'For a success status it returns the response itself (so calls can be chained); for '
        '1xx/3xx/4xx/5xx it raises HTTPStatusError with a message like "Client error ..."; it '
        'raises RuntimeError if the request instance has not been set on the response.',
        [HX + 'httpx/_models.py'],
        [
            'Cannot call `raise_for_status` as the request',
            'if self.is_success: return self',
            'raise HTTPStatusError(message, request=request, response=self)',
        ],
    ),
    (
        'code-httpx-timeout-hierarchy',
        'Which exception classes represent timeouts in httpx and what is their base class?',
        'ConnectTimeout, ReadTimeout, WriteTimeout and PoolTimeout, all subclasses of '
        'TimeoutException, which itself derives from TransportError → RequestError → HTTPError.',
        [HX + 'httpx/_exceptions.py', HX + 'docs/advanced/timeouts.md'],
        [
            'class TimeoutException(TransportError):',
            'class ConnectTimeout(TimeoutException):',
            'class PoolTimeout(TimeoutException):',
        ],
    ),
    (
        'code-httpx-httpstatuserror-base',
        'Is httpx.HTTPStatusError a subclass of RequestError?',
        'No. HTTPStatusError derives directly from HTTPError, while RequestError (and transport '
        'errors) is a separate branch under HTTPError.',
        [HX + 'httpx/_exceptions.py'],
        ['class HTTPStatusError(HTTPError):', 'class RequestError(HTTPError):'],
    ),
    (
        'code-httpx-digest-algorithms',
        'Which digest algorithms does httpx.DigestAuth support and what is the default?',
        'MD5, MD5-SESS, SHA, SHA-SESS, SHA-256, SHA-256-SESS, SHA-512 and SHA-512-SESS; if '
        'the server challenge does not specify an algorithm, MD5 is used.',
        [HX + 'httpx/_auth.py'],
        ['"SHA-512-SESS": hashlib.sha512', 'algorithm = header_dict.get("algorithm", "MD5")'],
    ),
    (
        'code-httpx-retries',
        'Does httpx retry failed requests, and which errors are retried?',
        'Not by default (`retries: int = 0` in HTTPTransport). With '
        '`httpx.HTTPTransport(retries=N)` only connection failures — ConnectError and '
        'ConnectTimeout — are retried; for read/write errors or 503 the docs suggest tools '
        'like tenacity.',
        [HX + 'httpx/_transports/default.py', HX + 'docs/advanced/transports.md'],
        [
            'retries: int = 0,',
            'Requests will be retried the given number of times in case an `httpx.ConnectError` '
            'or an `httpx.ConnectTimeout` occurs',
        ],
    ),
    (
        'code-httpx-default-encoding',
        'How does httpx decode response text when the server does not specify a charset?',
        'It falls back to the client/response `default_encoding`, which is "utf-8" by default; '
        'it can also be a callable that receives the bytes and returns an encoding (e.g. using '
        'chardet or charset-normalizer).',
        [HX + 'httpx/_models.py', HX + 'docs/advanced/text-encodings.md'],
        [
            'default_encoding: str | typing.Callable[[bytes], str] = "utf-8",',
            'Once `chardet` is installed, we can configure a client to use character-set '
            'autodetection.',
        ],
    ),
    (
        'code-httpx-ssl-cert-env',
        'Does httpx 0.28 use the SSL_CERT_FILE environment variable?',
        'In code, yes: `create_ssl_context` with `verify=True` and `trust_env=True` (the '
        'default) loads SSL_CERT_FILE or SSL_CERT_DIR if set, otherwise certifi. Note that the '
        'SSL documentation page still says that httpx does not pull these variables in '
        'automatically.',
        [HX + 'httpx/_config.py', HX + 'docs/advanced/ssl.md'],
        [
            'if trust_env and os.environ.get("SSL_CERT_FILE"):',
            'the `httpx` package does not automatically pull in',
        ],
    ),
    (
        'code-httpx-verify-false',
        'What SSL context does httpx create when verify=False is passed?',
        'A plain `ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` with `check_hostname = False` and '
        '`verify_mode = ssl.CERT_NONE`.',
        [HX + 'httpx/_config.py'],
        [
            'ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)',
            'ctx.check_hostname = False',
            'ctx.verify_mode = ssl.CERT_NONE',
        ],
    ),
    (
        'code-httpx-is-redirect',
        'What is the difference between Response.is_redirect and has_redirect_location?',
        '`is_redirect` is True for any 3xx status code, but not all 3xx responses are real URL '
        'redirects; `has_redirect_location` checks for a proper redirect with a Location header.',
        [HX + 'httpx/_models.py'],
        [
            'A property which is `True` for 3xx status codes, `False` otherwise.',
            'Note that not all responses with a 3xx status code indicate a URL redirect.',
        ],
    ),
    (
        'code-httpx-headers-get-list',
        'How can I get all values of a repeated header from httpx Headers?',
        'Use `Headers.get_list(key, split_commas=False)`; with `split_commas=True` '
        'comma-separated values are split into separate items.',
        [HX + 'httpx/_models.py'],
        ['def get_list(self, key: str, split_commas: bool = False) -> list[str]:'],
    ),
    (
        'code-httpx-queryparams-merge',
        'Does QueryParams.merge() modify the existing httpx.QueryParams instance?',
        'No, QueryParams is immutable: `merge()` returns a new QueryParams instance with the '
        'merged parameters.',
        [HX + 'httpx/_urls.py'],
        ['def merge(self, params: QueryParamTypes | None = None) -> QueryParams:'],
    ),
    # --- httpx: документация ---
    (
        'code-httpx-timeout-types',
        'What kinds of timeouts can be configured in httpx?',
        'Four: connect, read, write and pool timeouts; exceeding them raises ConnectTimeout, '
        'ReadTimeout, WriteTimeout or PoolTimeout respectively.',
        [HX + 'docs/advanced/timeouts.md'],
        [
            'There are four different types of timeouts that may occur. These are **connect**, '
            '**read**, **write**, and **pool** timeouts.'
        ],
    ),
    (
        'code-httpx-http2',
        'How do I enable HTTP/2 in httpx?',
        'Install the optional extra with `pip install httpx[http2]` and create the client with '
        '`http2=True`, e.g. `httpx.AsyncClient(http2=True)`; HTTP/2 is off by default.',
        [HX + 'docs/http2.md', HX + 'httpx/_client.py'],
        ['$ pip install httpx[http2]', 'client = httpx.AsyncClient(http2=True)'],
    ),
    (
        'code-httpx-event-hooks',
        'How can I log every request and response made by an httpx client?',
        'Use event hooks: `httpx.Client(event_hooks={"request": [log_request], "response": '
        '[log_response]})`; hooks can also be changed later through `client.event_hooks`.',
        [HX + 'docs/advanced/event-hooks.md'],
        [
            "client = httpx.Client(event_hooks={'request': [log_request], "
            "'response': [log_response]})"
        ],
    ),
    (
        'code-httpx-netrc',
        'How do I use credentials from a .netrc file with httpx?',
        'Pass `auth=httpx.NetRCAuth()` (default ~/.netrc) or `httpx.NetRCAuth(file=...)`, e.g. '
        'with the path from the NETRC environment variable; it relies on the standard '
        'library `netrc.netrc()`.',
        [HX + 'docs/advanced/authentication.md'],
        [
            '>>> auth = httpx.NetRCAuth(file="/path/to/.netrc")',
            'auth = httpx.NetRCAuth(file=os.environ.get("NETRC"))',
        ],
    ),
    (
        'code-httpx-asgi-transport',
        'How can I test an ASGI app with httpx without starting a server, and how do I set the '
        'client IP address?',
        'Use `httpx.ASGITransport(app=app)` with `httpx.AsyncClient(transport=transport, '
        'base_url="http://testserver")`; set the client address with `client=("1.2.3.4", 123)`, '
        'mount at a subpath with `root_path`, and inspect 500 responses with '
        '`raise_app_exceptions=False`.',
        [HX + 'docs/advanced/transports.md', HX + 'httpx/_transports/asgi.py'],
        [
            'transport = httpx.ASGITransport(app=app, client=("1.2.3.4", 123))',
            'Inspect 500 error responses rather than raise exceptions by setting '
            '`raise_app_exceptions=False`.',
        ],
    ),
    (
        'code-httpx-mounts-schemes',
        'How do mount keys in httpx differ from requests when mapping transports?',
        'httpx uses full URL schemes such as `mounts={"http://": ..., "https://": ...}` (and '
        'patterns like "all://"), and `Client.request()` does not accept `mounts=...`.',
        [HX + 'docs/compatibility.md'],
        [
            'we use full URL schemes, such as `mounts={"http://": ..., "https://": ...}`.',
            'whereas `httpx.Client.request(...)` does not allow `mounts=...`.',
        ],
    ),
    (
        'code-httpx-request-params',
        'Which parameters are not supported by the httpx.Request() constructor?',
        '`auth`, `timeout`, `follow_redirects`, `mounts`, `verify` and `cert`; they are '
        'available on `httpx.request`, `httpx.get`, `httpx.post` etc. and on the client.',
        [HX + 'docs/compatibility.md'],
        [
            '`httpx.Request()` does not support the `auth`, `timeout`, `follow_redirects`, '
            '`mounts`, `verify` and `cert` parameters.'
        ],
    ),
    # --- click: исходный код ---
    (
        'code-click-exit-codes',
        'What exit codes does click use for ClickException and UsageError?',
        'ClickException has exit_code = 1; UsageError (and its subclasses like BadParameter) '
        'uses exit_code = 2.',
        [CL + 'src/click/exceptions.py'],
        [
            ('class ClickException(Exception):', 'exit_code = 1'),
            ('class UsageError(ClickException):', 'exit_code = 2'),
        ],
    ),
    (
        'code-click-exception-hierarchy',
        'Which click exceptions are subclasses of UsageError?',
        'BadParameter (and MissingParameter, which extends BadParameter), NoSuchOption, '
        'BadOptionUsage and BadArgumentUsage. FileError extends ClickException directly; '
        'Abort and Exit extend RuntimeError.',
        [CL + 'src/click/exceptions.py'],
        [
            'class BadParameter(UsageError):',
            'class MissingParameter(BadParameter):',
            'class NoSuchOption(UsageError):',
            'class BadOptionUsage(UsageError):',
            'class BadArgumentUsage(UsageError):',
            'class FileError(ClickException):',
            'class Abort(RuntimeError):',
            'class Exit(RuntimeError):',
        ],
    ),
    (
        'code-click-help-option-names',
        'What is the default help option name in click, and how is it inherited?',
        '`["--help"]`; if `help_option_names` is not passed, the context takes it from the '
        'parent context, otherwise defaults to `["--help"]`. It can be changed via '
        'context_settings, e.g. `help_option_names=["-h", "--help"]`.',
        [CL + 'src/click/core.py'],
        [
            'help_option_names = parent.help_option_names',
            'help_option_names = ["--help"]',
        ],
    ),
    (
        'code-click-max-content-width',
        'What is the default maximum width of click help pages?',
        '80 characters: `max_content_width` defaults to 80 if not overridden, even if the '
        'terminal is wider; `terminal_width` is inherited from the parent or auto-detected.',
        [CL + 'src/click/core.py'],
        ['This defaults to 80 characters if not overridden.'],
    ),
    (
        'code-click-complete-var',
        'Which environment variable triggers shell completion for a click program named "foo-bar"?',
        '`_FOO_BAR_COMPLETE`: the variable name is `_{PROG_NAME}_COMPLETE` uppercased, with '
        'dashes (and dots) replaced by underscores; e.g. '
        '`eval "$(_FOO_BAR_COMPLETE=bash_source foo-bar)"`.',
        [CL + 'src/click/core.py', CL + 'docs/shell-completion.rst'],
        [
            'complete_var = f"_{complete_name}_COMPLETE".upper()',
            'eval "$(_FOO_BAR_COMPLETE=bash_source foo-bar)"',
        ],
    ),
    (
        'code-click-auto-envvar',
        'How does click build environment variable names from auto_envvar_prefix?',
        'The prefix is uppercased and dashes become underscores; nested commands append '
        '`_{COMMAND}`, and options read `{prefix}_{OPTION_NAME}` with the option name '
        'uppercased.',
        [CL + 'src/click/core.py'],
        [
            'auto_envvar_prefix = auto_envvar_prefix.upper()',
            'envvar = f"{ctx.auto_envvar_prefix}_{self.name.upper()}"',
        ],
    ),
    (
        'code-click-clirunner-exceptions',
        'What exit code does CliRunner.invoke report when the command raises an unexpected '
        'exception, and how can I make the exception propagate?',
        'exit_code is 1 and the exception is stored in `result.exception`; pass '
        '`catch_exceptions=False` to re-raise it. A SystemExit with a non-integer code is '
        'printed to stdout and also mapped to exit code 1.',
        [CL + 'src/click/testing.py'],
        ['catch_exceptions: bool = True,', 'if not catch_exceptions: raise'],
    ),
    (
        'code-click-mix-stderr',
        'Does click CliRunner capture stderr separately from stdout by default (click 8.1)?',
        'No, `mix_stderr` defaults to True, so stderr is mixed into the output; set '
        '`mix_stderr=False` to get stdout and stderr separately.',
        [CL + 'src/click/testing.py'],
        ['mix_stderr: bool = True,', ':param mix_stderr: if this is set to `False`'],
    ),
    (
        'code-click-get-app-dir',
        'Where does click.get_app_dir("Foo Bar") put the config folder on Linux, macOS and '
        'Windows?',
        'Unix: ~/.config/foo-bar; macOS: ~/Library/Application Support/Foo Bar; Windows: '
        'AppData\\Roaming\\Foo Bar (or AppData\\Local if roaming=False). With force_posix=True '
        'POSIX systems use ~/.foo-bar.',
        [CL + 'src/click/utils.py'],
        [
            '``~/.config/foo-bar``',
            '``~/Library/Application Support/Foo Bar``',
            'key = "APPDATA" if roaming else "LOCALAPPDATA"',
        ],
    ),
    (
        'code-click-choice-case',
        'Is click.Choice case sensitive by default?',
        'Yes, `case_sensitive: bool = True`; with `case_sensitive=False` values are compared '
        'after lowercasing (and after `token_normalize_func` if set).',
        [CL + 'src/click/types.py'],
        ['def __init__(self, choices: t.Sequence[str], case_sensitive: bool = True) -> None:'],
    ),
    (
        'code-click-path-allow-dash',
        'How do I make a click.Path parameter accept "-" for stdin/stdout and return an '
        'absolute path?',
        'Use `click.Path(allow_dash=True, resolve_path=True)`; both default to False.',
        [CL + 'src/click/types.py'],
        ['resolve_path: bool = False,', 'allow_dash: bool = False,'],
    ),
    # --- click: документация ---
    (
        'code-click-invoke-without-command',
        'What happens when a click group is called without a subcommand, and how can I run '
        'the group callback anyway?',
        'By default the group is not invoked and `--help` is shown; pass '
        '`invoke_without_command=True` to always invoke the callback '
        '(ctx.invoked_subcommand tells whether a subcommand follows).',
        [CL + 'docs/commands.rst'],
        [
            'not providing a command automatically passes ``--help`` by default.',
            '@click.group(invoke_without_command=True)',
        ],
    ),
    (
        'code-click-chain',
        'How do I run several click subcommands in one invocation and what are the restrictions?',
        'Use `@click.group(chain=True)`; only the last command may use `nargs=-1` on an '
        'argument, and multi commands cannot be nested below chained multicommands.',
        [CL + 'docs/commands.rst'],
        [
            '@click.group(chain=True)',
            'When using multi command chaining you can only have one command (the last) use '
            '``nargs=-1`` on an argument.',
        ],
    ),
    (
        'code-click-count',
        'How do I implement a -vvv verbosity flag in click?',
        "Use a counting option: `@click.option('-v', '--verbose', count=True)`.",
        [CL + 'docs/options.rst'],
        ["@click.option('-v', '--verbose', count=True)"],
    ),
    (
        'code-click-password',
        'How do I ask for a password twice with hidden input in click?',
        'Use an option with `prompt=True, hide_input=True, confirmation_prompt=True`, or the '
        '`@click.password_option()` decorator.',
        [CL + 'docs/options.rst'],
        ['"--password", prompt=True, hide_input=True,', '@click.password_option()'],
    ),
    (
        'code-click-intrange-clamp',
        'How can I make click clamp out-of-range integers instead of failing?',
        'Use `click.IntRange(min, max, clamp=True)`, e.g. '
        '`type=click.IntRange(0, 20, clamp=True)`; clamp is False by default.',
        [CL + 'docs/options.rst', CL + 'src/click/types.py'],
        ['@click.option("--count", type=click.IntRange(0, 20, clamp=True))'],
    ),
    (
        'code-click-isolated-fs',
        'How do I test a click command that creates files without touching the real working '
        'directory?',
        'Use `with runner.isolated_filesystem():` (optionally `temp_dir=tmp_path`), which sets '
        'the current working directory to a new empty folder.',
        [CL + 'docs/testing.rst'],
        [
            'method is useful for setting the current working directory to a new, empty folder.',
            'with runner.isolated_filesystem(temp_dir=tmp_path) as td:',
        ],
    ),
    (
        'code-click-echo-ansi',
        'Does click.echo keep ANSI color codes when output is redirected to a file?',
        'No, echo automatically strips ANSI color codes if the stream is not connected to a '
        'terminal.',
        [CL + 'docs/utils.rst'],
        [
            "Click's :func:`echo` function will automatically strip ANSI color codes if the "
            'stream is not connected to a terminal.'
        ],
    ),
    # --- Вопросы на две библиотеки ---
    (
        'code-cross-testing',
        'How do httpx and click let you test applications in-process without real network or '
        'terminal I/O?',
        'httpx: route requests directly to an ASGI app with `httpx.ASGITransport(app=app)`; '
        'click: `CliRunner().invoke()` runs the command in an isolated environment and '
        'captures output and exit code.',
        [HX + 'docs/advanced/transports.md', CL + 'docs/testing.rst'],
        ['transport = httpx.ASGITransport(app=app)', 'runner = CliRunner()'],
    ),
]
