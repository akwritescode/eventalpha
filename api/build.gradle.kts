plugins {
    java
    alias(libs.plugins.spring.boot)
    alias(libs.plugins.spring.dependency.management)
}

group = "com.eventalpha"
version = "0.1.0"
description = "EventAlpha read API"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation(libs.springdoc.webmvc)
    implementation(libs.anthropic)
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("org.springframework.boot:spring-boot-starter-jdbc-test")
    testImplementation("org.springframework.boot:spring-boot-starter-data-redis-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-postgresql")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test> {
    useJUnitPlatform()
}

// The warehouse schema is owned by Alembic (../migrations). Tests load the DDL that Alembic
// generates offline, so the Java read models are checked against the real schema.
val alembicSchema = layout.projectDirectory.file("src/test/resources/db/schema.sql")
tasks.named<Test>("test") {
    inputs.file(alembicSchema)
    inputs.file("../config/index_members.json")
}

tasks.processTestResources {
    from("../examples/move-window.sql") {
        into("db")
    }
}
