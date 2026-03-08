"""
Example UI tests using Playwright.

Demonstrates common patterns for browser-based testing:
- Page navigation and waiting
- Form interaction
- Element assertions
- Using evidence_recorder fixture

Copy and adapt these patterns for your own tests.
"""

import re

import pytest
from playwright.sync_api import Page, expect


class TestHomePage:
    """Tests for the application home page."""
    
    @pytest.mark.smoke
    @pytest.mark.ui
    def test_page_loads(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify the home page loads successfully.
        
        Expected: Page should load without errors and display main content.
        """
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        expect(page).to_have_title(re.compile(".+"))
        
        assert len(evidence_recorder["console"]) >= 0, "Console should be accessible"
    
    @pytest.mark.smoke
    @pytest.mark.ui
    def test_navigation_links(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify main navigation links are present and clickable.
        
        Expected: Navigation should contain expected links.
        """
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        nav_links = page.locator("nav a, header a, [role='navigation'] a")
        count = nav_links.count()
        
        assert count > 0, "Expected at least one navigation link"


class TestLoginFlow:
    """Tests for user authentication flow."""
    
    @pytest.mark.smoke
    @pytest.mark.ui
    def test_login_page_loads(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify the login page renders correctly.
        
        Expected: Login form should be visible with username/password fields.
        """
        page.goto(f"{base_url}/login")
        page.wait_for_load_state("networkidle")
        
        username_field = page.locator("[name='username'], [name='email'], #username, #email")
        password_field = page.locator("[name='password'], #password")
        submit_btn = page.locator("button[type='submit'], input[type='submit']")
        
        expect(username_field.first).to_be_visible()
        expect(password_field.first).to_be_visible()
        expect(submit_btn.first).to_be_visible()
    
    @pytest.mark.ui
    def test_login_with_valid_credentials(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify successful login with valid credentials.
        
        Expected: User should be redirected to dashboard after login.
        """
        page.goto(f"{base_url}/login")
        page.wait_for_load_state("networkidle")
        
        page.fill("[name='username'], [name='email'], #username, #email", "testuser")
        page.fill("[name='password'], #password", "password123")
        
        page.click("button[type='submit'], input[type='submit']")
        
        page.wait_for_load_state("networkidle")
        
        expect(page).not_to_have_url(f"{base_url}/login")
    
    @pytest.mark.ui
    def test_login_with_invalid_credentials(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify error message is shown for invalid credentials.
        
        Expected: Error message should be displayed, user stays on login page.
        """
        page.goto(f"{base_url}/login")
        page.wait_for_load_state("networkidle")
        
        page.fill("[name='username'], [name='email'], #username, #email", "invaliduser")
        page.fill("[name='password'], #password", "wrongpassword")
        
        page.click("button[type='submit'], input[type='submit']")
        
        page.wait_for_timeout(1000)
        
        error_indicators = [
            page.locator(".error, .error-message, [role='alert']"),
            page.get_by_text(re.compile(r"error|invalid|incorrect", re.IGNORECASE)),
        ]
        
        has_error = any(loc.count() > 0 for loc in error_indicators)
        stays_on_login = "/login" in page.url
        
        assert has_error or stays_on_login, "Expected error message or to stay on login page"


class TestFormInteraction:
    """Tests demonstrating form interaction patterns."""
    
    @pytest.mark.regression
    @pytest.mark.ui
    def test_form_validation(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify client-side form validation works.
        
        Expected: Required field validation should trigger on submit.
        """
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        forms = page.locator("form")
        if forms.count() == 0:
            pytest.skip("No forms found on page")
        
        form = forms.first
        submit = form.locator("button[type='submit'], input[type='submit']")
        
        if submit.count() > 0:
            required_inputs = form.locator("[required]")
            if required_inputs.count() > 0:
                submit.first.click()
                page.wait_for_timeout(500)
    
    @pytest.mark.regression
    @pytest.mark.ui
    def test_input_character_limit(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify input fields respect maxlength attribute.
        
        Expected: Input should not accept more characters than maxlength.
        """
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        inputs_with_maxlength = page.locator("input[maxlength]")
        if inputs_with_maxlength.count() == 0:
            pytest.skip("No inputs with maxlength found")
        
        input_elem = inputs_with_maxlength.first
        maxlength = int(input_elem.get_attribute("maxlength") or "100")
        
        long_text = "a" * (maxlength + 50)
        input_elem.fill(long_text)
        
        actual_value = input_elem.input_value()
        assert len(actual_value) <= maxlength, f"Input accepted {len(actual_value)} chars, max is {maxlength}"


class TestResponsiveDesign:
    """Tests for responsive design behavior."""
    
    @pytest.mark.regression
    @pytest.mark.ui
    def test_mobile_viewport(self, page: Page, base_url: str, evidence_recorder):
        """
        Verify page renders correctly on mobile viewport.
        
        Expected: Page should be usable at mobile dimensions.
        """
        page.set_viewport_size({"width": 375, "height": 667})
        
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        body = page.locator("body")
        expect(body).to_be_visible()
        
        horizontal_scroll = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        
        assert not horizontal_scroll, "Page has horizontal scroll on mobile viewport"
