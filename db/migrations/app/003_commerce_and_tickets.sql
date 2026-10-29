-- 003_commerce_and_tickets.sql
CREATE TABLE IF NOT EXISTS app.products (
    id UUID PRIMARY KEY,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    unit_price_minor BIGINT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'VND',
    stock_quantity INT NOT NULL DEFAULT 0,
    category TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES app.users(id),
    status TEXT NOT NULL DEFAULT 'placed',
    total_minor BIGINT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'VND',
    demo BOOLEAN NOT NULL DEFAULT TRUE,
    shipping_address JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON app.orders (customer_id);

CREATE TABLE IF NOT EXISTS app.order_items (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES app.orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES app.products(id),
    quantity INT NOT NULL,
    unit_price_minor BIGINT NOT NULL,
    total_minor BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON app.order_items (order_id);

CREATE TABLE IF NOT EXISTS app.shipments (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES app.orders(id) ON DELETE CASCADE,
    tracking_code TEXT,
    carrier TEXT,
    status TEXT NOT NULL,
    estimated_delivery TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.refunds (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES app.orders(id) ON DELETE CASCADE,
    amount_minor BIGINT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.tickets (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES app.users(id),
    order_id UUID REFERENCES app.orders(id),
    assigned_agent_id UUID REFERENCES app.users(id),
    handling_queue TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'normal',
    context_version INT NOT NULL DEFAULT 1,
    version INT NOT NULL DEFAULT 1,
    current_run_id UUID,
    current_decision_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tickets_customer_composite ON app.tickets (customer_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_queue_composite ON app.tickets (handling_queue, status, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS app.messages (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES app.tickets(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL,
    sender_role TEXT NOT NULL,
    content_ciphertext BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_ticket_composite ON app.messages (ticket_id, created_at, id);
