# Transfer-fax-app
: Pharmacy Prescription Transfer Fax Generator

## Email-code sign-in (Auth0)

Google sign-in stays as-is. A second sidebar button, "Sign in with email code", appears once
this block is added to Streamlit secrets (under the existing `[auth]` section):

```toml
[auth.auth0]
client_id = "dQwUrSnudg7VWRIIb5G87dWcSHv8g1Cm"
client_secret = "PASTE FROM AUTH0 > Applications > Rx Transfer Fax > Settings > Client Secret"
server_metadata_url = "https://dev-0s58a76adj0g3zxn.us.auth0.com/.well-known/openid-configuration"
authorize_params = { connection = "email" }
```

`authorize_params` sends Auth0 straight to the email-code screen (otherwise Universal Login may show only Google).

`redirect_uri` and `cookie_secret` are shared with Google (already in `[auth]`).
Never commit the real secret. Email-code sign-ins are written to SignInLog like Google ones.
