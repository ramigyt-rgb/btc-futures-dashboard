# =========================
# LOGIN SIMPLE
# =========================

def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode("utf-8")).hexdigest()


def init_users_file():
    if not os.path.exists(USERS_FILE):
        pd.DataFrame([
            {"usuario": "demo", "password_hash": hash_password("demo"), "rol": "cliente"}
        ]).to_csv(USERS_FILE, index=False)


def check_login(usuario, password):
    init_users_file()
    users = pd.read_csv(USERS_FILE)
    if users.empty:
        return False
    usuario = str(usuario)
    password_hash = hash_password(password)
    if "password_hash" in users.columns:
        ok = users[(users["usuario"].astype(str) == usuario) & (users["password_hash"].astype(str) == password_hash)]
        if len(ok) > 0:
            return True
    if "password" in users.columns:
        ok = users[(users["usuario"].astype(str) == usuario) & (users["password"].astype(str) == str(password))]
        if len(ok) > 0:
            return True
    return False
