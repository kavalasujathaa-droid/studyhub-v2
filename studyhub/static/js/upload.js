// StudyHub V2 - Direct Presigned R2 Uploader

document.addEventListener("DOMContentLoaded", () => {
    const subjectSelect = document.getElementById("uploadSubjectSelect");
    const titleSelect = document.getElementById("uploadTitleSelect");
    const uploadForm = document.getElementById("pdfUploadForm");
    const fileInput = document.getElementById("pdfFileInput");
    const progressContainer = document.getElementById("uploadProgressContainer");
    const progressBar = document.getElementById("uploadProgressBar");
    const progressStatus = document.getElementById("uploadStatusText");
    const uploadSubmitBtn = document.getElementById("uploadSubmitBtn");

    // 1. Dynamic Titles Lookup based on Selected Subject
    if (subjectSelect && titleSelect) {
        subjectSelect.addEventListener("change", async () => {
            const subjectId = subjectSelect.value;
            titleSelect.innerHTML = '<option value="">Loading titles...</option>';
            titleSelect.disabled = true;

            if (!subjectId) {
                titleSelect.innerHTML = '<option value="">-- First Select a Subject --</option>';
                return;
            }

            try {
                const res = await fetch(`/api/v1/subjects/${subjectId}/titles`);
                const data = await res.json();
                
                if (data.titles && data.titles.length > 0) {
                    titleSelect.innerHTML = '<option value="">-- Select Title --</option>';
                    data.titles.forEach(t => {
                        const opt = document.createElement("option");
                        opt.value = t.id;
                        opt.textContent = t.title_name;
                        titleSelect.appendChild(opt);
                    });
                    titleSelect.disabled = false;
                } else {
                    titleSelect.innerHTML = '<option value="">No titles found. Please add a title first.</option>';
                    titleSelect.disabled = true;
                }
            } catch (err) {
                titleSelect.innerHTML = '<option value="">Error loading titles.</option>';
            }
        });
    }

    // 2. Client-side File Validation on Select
    if (fileInput) {
        fileInput.addEventListener("change", () => {
            const file = fileInput.files[0];
            if (!file) return;

            if (!file.name.toLowerCase().endsWith(".pdf")) {
                alert("Only valid PDF files (.pdf) are allowed.");
                fileInput.value = "";
                return;
            }

            const maxBytes = 100 * 1024 * 1024; // 100 MB
            if (file.size > maxBytes) {
                alert("Selected file exceeds the maximum 100 MB limit.");
                fileInput.value = "";
                return;
            }

            // Auto-fill PDF title if empty
            const titleField = document.getElementById("pdfTitleInput");
            if (titleField && !titleField.value) {
                const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
                titleField.value = cleanName;
            }
        });
    }

    // 3. Form Submission with Direct Presigned PUT to R2
    if (uploadForm) {
        uploadForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const file = fileInput.files[0];
            const subjectId = subjectSelect.value;
            const titleId = titleSelect.value;
            const pdfTitle = document.getElementById("pdfTitleInput").value.trim();
            const description = document.getElementById("pdfDescriptionInput").value.trim();
            const isPublished = document.getElementById("pdfPublishedCheck").checked;

            if (!file || !subjectId || !titleId || !pdfTitle) {
                alert("Please complete all required fields.");
                return;
            }

            // Disable button & show progress
            uploadSubmitBtn.disabled = true;
            progressContainer.classList.remove("d-none");
            progressBar.style.width = "5%";
            progressBar.className = "progress-bar progress-bar-striped progress-bar-animated bg-primary";
            progressStatus.textContent = "Step 1/3: Requesting secure storage authorization...";

            try {
                // Step 1: Request presigned PUT URL
                const presignedRes = await fetch("/api/v1/storage/presigned-upload", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": window.getCSRFToken()
                    },
                    body: JSON.stringify({
                        subject_id: subjectId,
                        title_id: titleId,
                        file_size: file.size,
                        filename: file.name
                    })
                });

                const presignedData = await presignedRes.json();
                if (!presignedRes.ok) {
                    throw new Error(presignedData.error || "Failed to obtain upload authorization.");
                }

                const { upload_url, storage_key } = presignedData;

                // Step 2: Upload directly to Cloudflare R2
                progressStatus.textContent = "Step 2/3: Uploading PDF to private storage...";
                await new Promise((resolve, reject) => {
                    const xhr = new XMLHttpRequest();
                    xhr.open("PUT", upload_url, true);
                    xhr.setRequestHeader("Content-Type", "application/pdf");

                    xhr.upload.onprogress = (ev) => {
                        if (ev.lengthComputable) {
                            const percent = Math.round((ev.loaded / ev.total) * 85);
                            progressBar.style.width = `${Math.max(10, percent)}%`;
                            progressStatus.textContent = `Uploading: ${percent}% (${(ev.loaded / (1024*1024)).toFixed(1)} MB / ${(ev.total / (1024*1024)).toFixed(1)} MB)`;
                        }
                    };

                    xhr.onload = () => {
                        if (xhr.status >= 200 && xhr.status < 300) {
                            resolve();
                        } else {
                            reject(new Error(`Storage service rejected upload with status ${xhr.status}.`));
                        }
                    };

                    xhr.onerror = () => reject(new Error("Network failure during file upload to storage."));
                    xhr.send(file);
                });

                // Step 3: Complete upload and trigger backend validation
                progressBar.style.width = "90%";
                progressStatus.textContent = "Step 3/3: Verifying PDF signature and recording metadata...";

                const completeRes = await fetch("/api/v1/storage/complete-upload", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": window.getCSRFToken()
                    },
                    body: JSON.stringify({
                        subject_id: subjectId,
                        title_id: titleId,
                        title: pdfTitle,
                        description: description,
                        storage_key: storage_key,
                        original_filename: file.name,
                        is_published: isPublished
                    })
                });

                const completeData = await completeRes.json();
                if (!completeRes.ok) {
                    throw new Error(completeData.error || "Failed to finalize upload.");
                }

                // Success!
                progressBar.style.width = "100%";
                progressBar.className = "progress-bar bg-success";
                progressStatus.textContent = "Upload and verification complete! Redirecting...";

                setTimeout(() => {
                    window.location.href = "/admin/materials";
                }, 1000);

            } catch (err) {
                progressBar.className = "progress-bar bg-danger";
                progressStatus.textContent = `Error: ${err.message}`;
                uploadSubmitBtn.disabled = false;
                alert(`Upload failed: ${err.message}`);
            }
        });
    }
});
