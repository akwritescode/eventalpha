plugins {
    // Lets the toolchain below download JDK 25 when the machine doesn't have it.
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "eventalpha-api"
