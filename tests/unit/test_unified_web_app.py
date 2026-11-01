import unittest
import base64
from pathlib import Path
from api.main import (
    get_profile,
    update_profile,
    upload_and_parse_document,
    chat_with_agent,
    list_available_services,
    solve_human_gate,
    DocumentUploadRequest,
    ChatMessageRequest,
    GateSolveRequest
)

class TestUnifiedWebApp(unittest.TestCase):

    def setUp(self):
        self.profile_path = Path(__file__).resolve().parents[2] / "data" / "citizen.json"
        if self.profile_path.exists():
            with open(self.profile_path, "r", encoding="utf-8") as f:
                self.original_profile = f.read()
        else:
            self.original_profile = None

    def tearDown(self):
        if self.original_profile and self.profile_path.exists():
            with open(self.profile_path, "w", encoding="utf-8") as f:
                f.write(self.original_profile)

    def test_get_and_update_profile(self):
        # 1. GET profile
        data = get_profile()
        self.assertIn("personal", data)

        # 2. Update profile
        updated_data = dict(data)
        updated_data["personal"]["full_name"] = "Unified Test Citizen"
        res_post = update_profile(updated_data)
        self.assertEqual(res_post["status"], "success")

        # 3. Verify
        verify = get_profile()
        self.assertEqual(verify["personal"]["full_name"], "Unified Test Citizen")

    def test_upload_doc_endpoint(self):
        sample_text = """
        GOVERNMENT OF NCT OF DELHI
        TRANSPORT DEPARTMENT
        DRIVING LICENCE
        DL Number: DL-0420110012345
        Holder's Name: ANANYA GUPTA
        Date of Birth: 22/07/2000
        State: Delhi
        """
        b64 = base64.b64encode(sample_text.encode("utf-8")).decode("utf-8")
        req = DocumentUploadRequest(
            filename="sample_dl.txt",
            content_base64=b64
        )
        res = upload_and_parse_document(req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["extracted_entities"]["dl_number"], "DL0420110012345")
        self.assertEqual(res["extracted_entities"]["full_name"], "ANANYA GUPTA")
        self.assertEqual(res["extracted_entities"]["state"], "Delhi")

    def test_chat_endpoint_dl_intent(self):
        req = ChatMessageRequest(message="Please renew my driving license DL-0420110012345 on Parivahan")
        res = chat_with_agent(req)
        self.assertEqual(res["service_recommendation"], "parivahan_dl")
        self.assertIn("Parivahan", res["reply"])
        self.assertEqual(res["extracted_entities"]["dl_number"], "DL0420110012345")

    def test_chat_endpoint_url_intent(self):
        req = ChatMessageRequest(message="Fill this form: https://httpbin.org/forms/post")
        res = chat_with_agent(req)
        self.assertEqual(res["service_recommendation"], "universal")
        self.assertEqual(res["target_url"], "https://httpbin.org/forms/post")

    def test_services_catalog_endpoint(self):
        services = list_available_services()
        self.assertTrue(len(services) >= 3)
        service_ids = [s.service_id for s in services]
        self.assertIn("scholarship", service_ids)
        self.assertIn("license_renewal", service_ids)

    def test_gate_solve_endpoint(self):
        req = GateSolveRequest(run_id="active", captcha="AB12CD", action="approve")
        res = solve_human_gate(req)
        self.assertEqual(res["status"], "success")

if __name__ == "__main__":
    unittest.main()
