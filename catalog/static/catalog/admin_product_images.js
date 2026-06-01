(function () {
    "use strict";

    function getInlineGroups() {
        return Array.from(document.querySelectorAll(".inline-group"))
            .filter(function (group) {
                return group.querySelector('input[name$="-sort_order"]');
            });
    }

    function getRows(group) {
        return Array.from(group.querySelectorAll("tr.form-row, tr.dynamic-images, .dynamic-images"))
            .filter(function (row) {
                return row.querySelector('input[name$="-sort_order"]')
                    && !row.classList.contains("empty-form")
                    && row.id.indexOf("__prefix__") === -1;
            });
    }

    function rowIsDeleted(row) {
        var deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        return Boolean(deleteInput && deleteInput.checked);
    }

    function rowHasImage(row) {
        var existingFileLink = row.querySelector('.file-upload a[href], a[href*="/media/"]');
        var previewImage = row.querySelector("img.product-image-admin-preview");
        var fileInput = row.querySelector('input[type="file"]');

        return Boolean(existingFileLink || previewImage || (fileInput && fileInput.files && fileInput.files.length));
    }

    function updateOrderAndBadges(group) {
        var rows = getRows(group);
        var activeImageIndex = 0;

        rows.forEach(function (row) {
            var sortInput = row.querySelector('input[name$="-sort_order"]');
            var badge = row.querySelector(".product-image-main-badge");

            row.classList.remove("product-image-main-row");

            if (!sortInput) {
                return;
            }

            if (rowIsDeleted(row) || !rowHasImage(row)) {
                if (badge) {
                    badge.textContent = "—";
                    badge.classList.remove("is-main");
                }
                return;
            }

            sortInput.value = activeImageIndex;

            if (badge) {
                if (activeImageIndex === 0) {
                    badge.textContent = "Главная";
                    badge.classList.add("is-main");
                    row.classList.add("product-image-main-row");
                } else {
                    badge.textContent = "Доп.";
                    badge.classList.remove("is-main");
                }
            }

            activeImageIndex += 1;
        });
    }

    function getDragAfterRow(container, y) {
        var rows = Array.from(container.querySelectorAll("tr.product-image-draggable-row:not(.is-dragging)"));

        return rows.reduce(function (closest, child) {
            var box = child.getBoundingClientRect();
            var offset = y - box.top - box.height / 2;

            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            }

            return closest;
        }, { offset: Number.NEGATIVE_INFINITY, element: null }).element;
    }

    function initGroup(group) {
        var rows = getRows(group);
        var tbody = group.querySelector("tbody") || group;

        rows.forEach(function (row) {
            if (row.dataset.dragImagesReady === "1") {
                return;
            }

            row.dataset.dragImagesReady = "1";
            row.classList.add("product-image-draggable-row");

            var handle = row.querySelector(".product-image-drag-handle");
            if (handle) {
                handle.addEventListener("mousedown", function () {
                    row.draggable = true;
                });

                handle.addEventListener("touchstart", function () {
                    row.draggable = true;
                }, { passive: true });
            }

            row.addEventListener("dragstart", function (event) {
                if (!row.draggable || rowIsDeleted(row)) {
                    event.preventDefault();
                    return;
                }

                row.classList.add("is-dragging");
                event.dataTransfer.effectAllowed = "move";
            });

            row.addEventListener("dragend", function () {
                row.classList.remove("is-dragging");
                row.draggable = false;
                updateOrderAndBadges(group);
            });

            row.addEventListener("change", function () {
                updateOrderAndBadges(group);
            });
        });

        tbody.addEventListener("dragover", function (event) {
            var draggingRow = group.querySelector(".is-dragging");
            if (!draggingRow) {
                return;
            }

            event.preventDefault();
            var afterRow = getDragAfterRow(tbody, event.clientY);

            if (afterRow === null) {
                tbody.appendChild(draggingRow);
            } else {
                tbody.insertBefore(draggingRow, afterRow);
            }
        });

        updateOrderAndBadges(group);
    }

    function initAll() {
        getInlineGroups().forEach(initGroup);
    }

    document.addEventListener("DOMContentLoaded", initAll);
    document.addEventListener("formset:added", initAll);
    document.addEventListener("formset:removed", initAll);
})();
