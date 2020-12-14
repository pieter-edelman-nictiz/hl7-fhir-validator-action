FROM ubuntu:20.10
RUN apt-get update && apt-get -y upgrade
RUN apt-get -y install wget
RUN apt-get -y install openjdk-11-jre-headless
RUN apt-get -y install python3

RUN mkdir /tools
RUN wget -nv https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar -O tools/validator.jar
RUN java -jar tools/validator.jar -version 4.0 | cat

COPY analyze_results.py /tools/analyze_results.py

RUN mkdir /output
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]