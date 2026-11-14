# Build with the Gradle wrapper on JDK 25, run on a JRE-only image.
FROM eclipse-temurin:25-jdk AS build
WORKDIR /src
COPY gradlew settings.gradle.kts build.gradle.kts ./
COPY gradle gradle
RUN ./gradlew --no-daemon dependencies > /dev/null   # cache dependencies in their own layer
COPY src src
RUN ./gradlew --no-daemon bootJar -x test && cp build/libs/*.jar /app.jar

FROM eclipse-temurin:25-jre
RUN useradd --system --uid 10001 app
USER app
COPY --from=build /app.jar /app.jar
EXPOSE 8081
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app.jar"]
