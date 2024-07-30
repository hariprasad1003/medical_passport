CREATE DATABASE healthcare_provider_system;
USE healthcare_provider_system;

DROP TABLE IF EXISTS patient;
DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS transfer_request;

CREATE TABLE healthcare_provider (
    healthcare_provider_id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    house_number_post_box_number VARCHAR(50) NOT NULL,
    post_code VARCHAR(100) NOT NULL,
    country VARCHAR(100) NOT NULL
);


CREATE TABLE user (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    email_id VARCHAR(100) NOT NULL
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL
);

CREATE TABLE patient (
    patient_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    healthcare_provider_id INT,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    date_of_birth DATE,
    house_number_post_box_number VARCHAR(50),
    post_code VARCHAR(10),
    age INT,
    gender VARCHAR(10),
    medical_condition VARCHAR(50),
    medical_procedure VARCHAR(50),
    cost DECIMAL(10, 2),
    length_of_stay INT,
    readmission BOOLEAN,
    outcome VARCHAR(50),
    satisfaction INT,
    FOREIGN KEY (user_id) REFERENCES user(user_id)
);

CREATE TABLE transfer_request (
    transfer_request_id INT PRIMARY KEY AUTO_INCREMENT,
    requested_healthcare_provider_id INT,
    transfer_request_type VARCHAR(50),
    patient_first_name VARCHAR(50),
    patient_last_name VARCHAR(50),
    patient_date_of_birth DATE,
    patient_house_number_post_box_number VARCHAR(50),
    patient_post_code VARCHAR(10),
    status VARCHAR(50)
);