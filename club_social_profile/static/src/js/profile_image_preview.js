/** @odoo-module **/
/*
 * Live preview of profile and cover images on the portal profile edit page.
 * When the user picks a file via <input type="file" data-preview-target="...">,
 * read it as a data URL and inject it as the <img src=""> of the targeted
 * preview container — no need to save the form to see the new image.
 */

function applyPreview(input) {
    const targetSelector = input.dataset.previewTarget;
    if (!targetSelector) return;
    const target = document.querySelector(targetSelector);
    if (!target) return;

    const file = input.files && input.files[0];
    if (!file) return;
    if (!file.type || !file.type.startsWith("image/")) return;

    const reader = new FileReader();
    reader.onload = (event) => {
        const dataUrl = event.target.result;
        // Replace the container's content with the new <img>, preserving sizing.
        target.innerHTML = "";
        const img = document.createElement("img");
        img.src = dataUrl;
        img.alt = "";
        img.className = "w-100 h-100";
        img.style.objectFit = "cover";
        target.appendChild(img);
    };
    reader.readAsDataURL(file);
}

function setup() {
    document.querySelectorAll('input[type="file"][data-preview-target]').forEach((input) => {
        input.addEventListener("change", () => applyPreview(input));
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
} else {
    setup();
}
