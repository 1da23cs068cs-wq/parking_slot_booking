-- ============================================================
-- Cloud-Based Parking Slot Booking System
-- Full MySQL Schema — AWS RDS Compatible
-- ============================================================

CREATE DATABASE IF NOT EXISTS parking_system;
USE parking_system;

-- ── Users Table ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    full_name   VARCHAR(100) NOT NULL,
    email       VARCHAR(150) NOT NULL UNIQUE,
    phone       VARCHAR(15),
    password    VARCHAR(255) NOT NULL,
    vehicle_no  VARCHAR(20),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active   TINYINT(1) DEFAULT 1
);

-- ── Admins Table ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admins (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50) NOT NULL UNIQUE,
    email       VARCHAR(150) NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Parking Slots Table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS parking_slots (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    slot_number  VARCHAR(20) NOT NULL UNIQUE,
    slot_type    ENUM('car','bike','ev') DEFAULT 'car',
    area         VARCHAR(50) DEFAULT 'Zone A',
    floor        VARCHAR(20) DEFAULT 'Ground',
    status       ENUM('available','occupied','reserved','maintenance') DEFAULT 'available',
    hourly_rate  DECIMAL(10,2) DEFAULT 20.00,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Bookings Table ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    booking_ref     VARCHAR(20) NOT NULL UNIQUE,
    user_id         INT NOT NULL,
    slot_id         INT NOT NULL,
    vehicle_no      VARCHAR(20) NOT NULL,
    booking_date    DATE NOT NULL,
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    duration_hours  DECIMAL(5,2),
    total_cost      DECIMAL(10,2) DEFAULT 0.00,
    status          ENUM('active','completed','cancelled') DEFAULT 'active',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES parking_slots(id) ON DELETE CASCADE,
    -- Prevent double-booking: same slot, overlapping times on same date
    UNIQUE KEY no_overlap (slot_id, booking_date, start_time, end_time)
);

-- ── Payments Table ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    booking_id     INT NOT NULL,
    amount         DECIMAL(10,2) NOT NULL,
    payment_method ENUM('cash','card','upi','wallet') DEFAULT 'cash',
    payment_status ENUM('pending','paid','refunded') DEFAULT 'pending',
    paid_at        DATETIME,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

-- ── Audit Logs Table ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT,
    action      VARCHAR(200) NOT NULL,
    table_name  VARCHAR(50),
    record_id   INT,
    details     TEXT,
    ip_address  VARCHAR(45),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- SAMPLE DATA
-- ============================================================

-- Admin account (password: admin123)
INSERT INTO admins (username, email, password) VALUES
('admin', 'admin@parkingsystem.com',
 'pbkdf2:sha256:600000$abc123$hashedpassword');

-- Parking Slots — Zone A (Cars)
INSERT INTO parking_slots (slot_number, slot_type, area, floor, status, hourly_rate) VALUES
('A-01', 'car', 'Zone A', 'Ground', 'available', 20.00),
('A-02', 'car', 'Zone A', 'Ground', 'available', 20.00),
('A-03', 'car', 'Zone A', 'Ground', 'occupied',  20.00),
('A-04', 'car', 'Zone A', 'Ground', 'available', 20.00),
('A-05', 'car', 'Zone A', 'Ground', 'reserved',  20.00),
('A-06', 'car', 'Zone A', 'Ground', 'available', 20.00),
('A-07', 'car', 'Zone A', 'Ground', 'available', 20.00),
('A-08', 'car', 'Zone A', 'Ground', 'occupied',  20.00),
-- Zone B (Cars — First Floor)
('B-01', 'car', 'Zone B', 'First',  'available', 25.00),
('B-02', 'car', 'Zone B', 'First',  'available', 25.00),
('B-03', 'car', 'Zone B', 'First',  'available', 25.00),
('B-04', 'car', 'Zone B', 'First',  'occupied',  25.00),
('B-05', 'car', 'Zone B', 'First',  'available', 25.00),
('B-06', 'car', 'Zone B', 'First',  'reserved',  25.00),
-- Zone C (Bikes)
('C-01', 'bike', 'Zone C', 'Ground', 'available', 10.00),
('C-02', 'bike', 'Zone C', 'Ground', 'available', 10.00),
('C-03', 'bike', 'Zone C', 'Ground', 'occupied',  10.00),
('C-04', 'bike', 'Zone C', 'Ground', 'available', 10.00),
('C-05', 'bike', 'Zone C', 'Ground', 'available', 10.00),
('C-06', 'bike', 'Zone C', 'Ground', 'available', 10.00),
-- Zone D (EV Charging)
('D-01', 'ev', 'Zone D', 'Ground', 'available', 40.00),
('D-02', 'ev', 'Zone D', 'Ground', 'available', 40.00),
('D-03', 'ev', 'Zone D', 'Ground', 'occupied',  40.00),
('D-04', 'ev', 'Zone D', 'Ground', 'available', 40.00);

-- Sample Users (password: password123 for all)
INSERT INTO users (full_name, email, phone, password, vehicle_no) VALUES
('Arjun Sharma',   'arjun@example.com',  '9876543210', 'pbkdf2:sha256:600000$salt1$hash1', 'KA01AB1234'),
('Priya Singh',    'priya@example.com',  '9876543211', 'pbkdf2:sha256:600000$salt2$hash2', 'MH02CD5678'),
('Rahul Verma',    'rahul@example.com',  '9876543212', 'pbkdf2:sha256:600000$salt3$hash3', 'DL03EF9012');

-- ============================================================
-- STORED PROCEDURE: Check slot availability
-- ============================================================
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS check_slot_availability(
    IN p_slot_id INT,
    IN p_date DATE,
    IN p_start TIME,
    IN p_end TIME,
    OUT p_available BOOLEAN
)
BEGIN
    DECLARE overlap_count INT;
    SELECT COUNT(*) INTO overlap_count
    FROM bookings
    WHERE slot_id = p_slot_id
      AND booking_date = p_date
      AND status != 'cancelled'
      AND (
          (start_time < p_end AND end_time > p_start)
      );
    SET p_available = (overlap_count = 0);
END //
DELIMITER ;
