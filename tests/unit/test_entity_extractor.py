import unittest
import base64
import json
from pathlib import Path
from agent.tools.entity_extractor import EntityExtractor

class TestEntityExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = EntityExtractor()

    def test_extract_dl_and_dob(self):
        sample = """
        GOVERNMENT OF NCT OF DELHI
        TRANSPORT DEPARTMENT
        DRIVING LICENCE
        DL Number: DL-0420110012345
        Holder's Name: RAHUL KUMAR
        Date of Birth: 05/08/1998
        Father's Name: RAMESH KUMAR
        State: Delhi
        """
        res = self.extractor.extract_from_text(sample)
        self.assertEqual(res.get("dl_number"), "DL0420110012345")
        self.assertEqual(res.get("full_name"), "RAHUL KUMAR")
        self.assertEqual(res.get("dob"), "05/08/1998")
        self.assertEqual(res.get("father_name"), "RAMESH KUMAR")
        self.assertEqual(res.get("state"), "Delhi")

    def test_extract_marksheet(self):
        sample = """
        STATE BOARD OF TECHNICAL EDUCATION
        Candidate Name: PRIYA VERMA
        College: Government Polytechnic Pune
        Course: Diploma in Computer Engineering
        Total Marks: 85.5%
        Annual Income: Rs. 350000
        State: Maharashtra
        """
        res = self.extractor.extract_from_text(sample)
        self.assertEqual(res.get("full_name"), "PRIYA VERMA")
        self.assertEqual(res.get("college"), "Government Polytechnic Pune")
        self.assertEqual(res.get("marks"), "85.5")
        self.assertEqual(res.get("annual_income"), "350000")
        self.assertEqual(res.get("state"), "Maharashtra")

    def test_base64_text_extraction(self):
        raw = "Name: AMIT SHARMA\nDL No: MH-1220190012345\nDOB: 12/04/1997\nState: Maharashtra"
        b64 = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        res = self.extractor.extract_from_base64(b64, filename="sample.txt")
        self.assertEqual(res.get("full_name"), "AMIT SHARMA")
        self.assertEqual(res.get("dl_number"), "MH1220190012345")
        self.assertEqual(res.get("dob"), "12/04/1997")

if __name__ == "__main__":
    unittest.main()
