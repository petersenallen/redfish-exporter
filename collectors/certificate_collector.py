from prometheus_client.core import GaugeMetricFamily

import logging
import ssl
import socket
import datetime

class CertificateCollector(object):

    def __init__(self, host, target, labels):
        self.host = host
        self.target = target
        self.timeout = 10
        self.labels = labels
        self.port = 443

        self.cert_metrics_isvalid = GaugeMetricFamily(
            "redfish_certificate_isvalid",
            "Redfish Server Monitoring certificate is valid",
            labels = self.labels,
        )
        self.cert_metrics_valid_hostname = GaugeMetricFamily(
            "redfish_certificate_valid_hostname",
            "Redfish Server Monitoring certificate has valid hostname",
            labels = self.labels,
        )
        self.cert_metrics_valid_days = GaugeMetricFamily(
            "redfish_certificate_valid_days",
            "Redfish Server Monitoring certificate valid for days",
            labels = self.labels,
        )
        self.cert_metrics_selfsigned = GaugeMetricFamily(
            "redfish_certificate_selfsigned",
            "Redfish Server Monitoring certificate is self-signed",
            labels = self.labels,
        )


    def collect(self):

        logging.info(f"Target {self.target}: Collecting data ...")

        context = ssl.create_default_context()
        context.check_hostname = False
        context.load_default_certs()
        default_path = ssl.get_default_verify_paths()
        logging.debug(f"Target {self.target}: Default cert path: {default_path}")
            
        context.load_verify_locations(cafile='/usr/local/share/ca-certificates/SAPNetCA_G2.crt')
        root_certificates = context.get_ca_certs()

        if root_certificates:
            for cert in root_certificates:
                issuer = dict(x[0] for x in cert['issuer'])
                logging.info(f"Target {self.target}: issuer name: {issuer.get('commonName')}")
        else:
            logging.info("No Root CA Certs found!")
            
        context.verify_mode = ssl.CERT_REQUIRED
        cert_days_left = 0
        cert_valid = 0
        cert_has_right_hostname = 0
        cert_selfsigned = 0
        current_labels = {
            "issuer": "n/a",
            "subject": "n/a",
            "not_after": "n/a",
        }

        try:
            sock = socket.socket(socket.AF_INET)
            sock.settimeout(self.timeout)
            conn = context.wrap_socket(sock, server_hostname=self.host)
            conn.connect((self.host, self.port))
            cert = conn.getpeercert()

        except ssl.SSLCertVerificationError as e:

            logging.debug(f"Target {self.target}: Certificate Validation Error!")
            logging.debug(f"Target {self.target}: Reason: {e.reason}")
            logging.debug(f"Target {self.target}: Verify Message: {e.verify_message}")

            if e.verify_message == 'self-signed certificate':
                cert_selfsigned = 1
                current_labels.update({"issuer": "self-signed"})

            elif e.verify_message == 'unable to get issuer certificate':
                cert = e.cert

            else:
                return

        except TimeoutError:
            logging.debug(f"Target {self.target}: Timeout occured!")
            return
        
        finally:
            conn.close()
            sock.close()

        if cert:
            cert_expiry_date = datetime.datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z') if 'notAfter' in cert else datetime.datetime.now()
            cert_days_left = (cert_expiry_date - datetime.datetime.now()).days
            issuer = dict(x[0] for x in cert['issuer'])
            subject = dict(x[0] for x in cert['subject'])
            current_labels.update(
                {
                    "issuer": issuer['commonName'],
                    "subject": subject['commonName'],
                    "not_after": cert_expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            if issuer['commonName'] == subject['commonName'] or subject['commonName'] == "www.example.org":
                cert_selfsigned = 1

            if subject['commonName'] == self.host:
                cert_has_right_hostname = 1

            if cert_days_left > 0 and cert_has_right_hostname:
                cert_valid = 1


        current_labels.update(self.labels)

        self.cert_metrics_isvalid.add_sample(
            "redfish_certificate_isvalid",
            value = cert_valid,
            labels = current_labels,
        )

        self.cert_metrics_valid_hostname.add_sample(
            "redfish_certificate_valid_hostname",
            value = cert_has_right_hostname,
            labels = current_labels,
        )

        self.cert_metrics_valid_days.add_sample(
            "redfish_certificate_valid_days",
            value = cert_days_left,
            labels = current_labels,
        )

        self.cert_metrics_selfsigned.add_sample(
            "redfish_certificate_selfsigned",
            value = cert_selfsigned,
            labels = current_labels,
        )
     
