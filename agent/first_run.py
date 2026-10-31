
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "data" / "citizen.json"


def load_profile():
    with open(PROFILE_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


async def main():
    profile = load_profile()
    personal = profile["personal"]
    education = profile["education"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        try:
            # 1. Login
            await page.goto("http://127.0.0.1:5000/login")

            await page.get_by_label("User ID").fill("student")
            await page.get_by_label("Password").fill("demo123")

            await page.get_by_role(
                "button", name="Sign in securely"
            ).click()

            print("SUCCESS: Logged in.")

            # 2. Personal information
            await page.get_by_label("Full name *").fill(
                personal["full_name"]
            )
            await page.get_by_label("Date of birth *").fill(
                personal["dob"]
            )
            await page.get_by_label("Category").select_option(
                label=personal["category"]
            )
            await page.get_by_label("Current course").select_option(
                label=personal["course"]
            )
            await page.get_by_label("State").select_option(
                label=personal["state"]
            )
            await page.get_by_label("District").select_option(
                label=personal["district"]
            )
            await page.get_by_label("Block / Taluka").select_option(
                label=personal["block"]
            )

            await page.get_by_role(
                "button", name="Save & continue"
            ).click()

            # 3. Verify education page
            await page.get_by_role(
                "heading",
                name="Academic information",
                exact=True
            ).wait_for()

            print("VERIFIED: Personal information submitted.")

            # 4. Education information
            await page.get_by_label(
                "College / Institution *"
            ).fill(education["college"])

            await page.get_by_label(
                "Current year"
            ).select_option(label=education["course_year"])

            await page.get_by_label(
                "Previous examination marks (%)"
            ).fill(education["marks"])

            await page.get_by_label(
                "Annual family income (₹)"
            ).fill(education["annual_income"])

            # 5. Upload marksheet
            marksheet_path = ROOT / education["marksheet_path"]

            assert marksheet_path.exists(), (
                f"Marksheet not found: {marksheet_path}"
            )

            upload = page.get_by_label("Upload marksheet")
            await upload.set_input_files(str(marksheet_path))

            uploaded_files = await upload.evaluate(
                "(element) => Array.from(element.files).map(f => f.name)"
            )

            assert marksheet_path.name in uploaded_files

            print("VERIFIED: Marksheet uploaded.")

            # 6. Verify education fields
            assert await page.get_by_label(
                "College / Institution *"
            ).input_value() == education["college"]

            assert await page.get_by_label(
                "Previous examination marks (%)"
            ).input_value() == education["marks"]

            assert await page.get_by_label(
                "Annual family income (₹)"
            ).input_value() == education["annual_income"]

            print("VERIFIED: Education fields contain expected values.")

            await page.screenshot(
                path=str(ROOT / "education_verified.png"),
                full_page=True
            )

            # 7. Declaration page
            await page.get_by_role(
                "button", name="Save & continue"
            ).click()

            await page.get_by_role(
                "heading", name="Declaration", exact=True
            ).wait_for()

            print("VERIFIED: Declaration page reached.")

            # 8. Accept declaration
            declaration = page.get_by_label(
                "I agree to the declaration."
            )

            await declaration.check()
            assert await declaration.is_checked()

            print("VERIFIED: Declaration accepted.")

            # 9. Review page
            await page.get_by_role(
                "button", name="Continue to review"
            ).click()

            await page.get_by_role(
                "heading", name="Review your application", exact=True
            ).wait_for()

            print("REACHED REVIEW PAGE:", page.url)

            await page.screenshot(
                path=str(ROOT / "review_page.png"),
                full_page=True
            )

            print("SUCCESS: Review page screenshot saved.")

            # 10. Human approval gate
            print("\nAPPLICATION READY FOR FINAL SUBMISSION.")
            print("Please review the application in the browser.")

            approval = input(
                "\nDo you approve submission? (yes/no): "
            ).strip().lower()

            if approval == "yes":

                await page.get_by_role(
                    "button",
                    name="Approve & submit application"
                ).click()

                await page.wait_for_load_state("domcontentloaded")

                print("SUBMISSION ACTION COMPLETED.")
                print("Final URL:", page.url)

                await page.screenshot(
                    path=str(ROOT / "submission_receipt.png"),
                    full_page=True
                )

                print("Receipt screenshot saved.")

            else:
                print("Submission cancelled.")
                print("Application remains unsubmitted.")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
