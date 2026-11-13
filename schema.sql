-- Runs on every app start; IF NOT EXISTS keeps it safe to re-run.
-- Added a column? Also list it in db.ADDED_COLUMNS so existing data.db files get it.
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT UNIQUE,
  cart_json TEXT,
  address TEXT,
  subtotal REAL,
  delivery_fee REAL,
  total REAL,
  timestamp TEXT,
  customer_name TEXT,
  phone TEXT,
  delivery_notes TEXT,
  card_brand TEXT,
  card_last4 TEXT,
  card_expiry TEXT
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE,
  name TEXT,
  password_hash TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS cards (
  id TEXT PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  brand TEXT,
  last4 TEXT,
  expiry TEXT
);
