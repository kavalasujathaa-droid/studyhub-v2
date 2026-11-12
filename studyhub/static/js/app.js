// StudyHub V2 Main Application Script

document.addEventListener("DOMContentLoaded", () => {
    // 1. Theme Management (Light / Dark)
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    const currentTheme = localStorage.getItem("studyhub_theme") || "light";
    document.documentElement.setAttribute("data-bs-theme", currentTheme);
    updateThemeIcon(currentTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            const activeTheme = document.documentElement.getAttribute("data-bs-theme");
            const newTheme = activeTheme === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-bs-theme", newTheme);
            localStorage.setItem("studyhub_theme", newTheme);
            updateThemeIcon(newTheme);
        });
    }

    function updateThemeIcon(theme) {
        const icon = document.getElementById("themeIcon");
        if (icon) {
            if (theme === "dark") {
                icon.className = "bi bi-sun-fill text-warning";
            } else {
                icon.className = "bi bi-moon-stars-fill text-secondary";
            }
        }
    }

    // 2. Global Helper for CSRF Token in AJAX Calls
    window.getCSRFToken = function() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    };

    // 3. Global Toast System
    window.showToast = function(message, type = "info") {
        const container = document.getElementById("toastContainer");
        if (!container) return;

        const toastEl = document.createElement("div");
        toastEl.className = `toast align-items-center text-bg-${type} border-0 show mb-2`;
        toastEl.setAttribute("role", "alert");
        toastEl.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        container.appendChild(toastEl);
        setTimeout(() => toastEl.remove(), 4000);
    };

    // 4. Student Bookmark AJAX Toggle
    document.querySelectorAll(".btn-bookmark-toggle").forEach(button => {
        button.addEventListener("click", async (e) => {
            e.preventDefault();
            const pdfId = button.getAttribute("data-pdf-id");
            if (!pdfId) return;

            try {
                const response = await fetch("/api/v1/bookmarks/toggle", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": window.getCSRFToken()
                    },
                    body: JSON.stringify({ pdf_id: pdfId })
                });

                const data = await response.json();
                if (response.ok && data.success) {
                    const icon = button.querySelector("i");
                    if (data.bookmarked) {
                        icon.className = "bi bi-bookmark-fill text-warning";
                        button.classList.add("active");
                        window.showToast("Bookmark added!", "success");
                    } else {
                        icon.className = "bi bi-bookmark text-secondary";
                        button.classList.remove("active");
                        window.showToast("Bookmark removed.", "info");
                    }
                } else {
                    window.showToast(data.error || "Failed to toggle bookmark.", "danger");
                }
            } catch (err) {
                window.showToast("Network error. Please try again.", "danger");
            }
        });
    });
});
