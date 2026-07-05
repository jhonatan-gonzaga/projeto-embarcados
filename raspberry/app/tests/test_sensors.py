import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.sensors import salvar_sensor_data


class SensorsTest(unittest.TestCase):
    def test_salvar_sensor_data_reconhece_mq9(self):
        payload = {"temperatura": 25.0, "humidade": 45.0, "mq9": 12.5}

        sensor_data = salvar_sensor_data(payload)

        self.assertEqual(sensor_data["co"], 12.5)
        self.assertEqual(sensor_data["co_ppm"], 12.5)

    def test_salvar_sensor_data_reconhece_mq9_ppm(self):
        payload = {"temperatura": 24.0, "umidade": 50.0, "mq9_ppm": 8.2}

        sensor_data = salvar_sensor_data(payload)

        self.assertEqual(sensor_data["co"], 8.2)
        self.assertEqual(sensor_data["co_ppm"], 8.2)


if __name__ == "__main__":
    unittest.main()
