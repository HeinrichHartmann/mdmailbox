;;; mdmailbox.el --- Major mode for composing emails with mdmailbox -*- lexical-binding: t; -*-

;; Author: Heinrich Hartmann <heinrich@heinrichhartmann.com>
;; Version: 0.1.0
;; Package-Requires: ((emacs "27.1"))
;; Keywords: mail, email, mdmailbox
;; Homepage: https://github.com/HeinrichHartmann/mdmailbox

;;; Commentary:
;; Major mode for editing and sending emails with mdmailbox.
;; Emails are stored as YAML frontmatter + Markdown body files.
;;
;; Features:
;;   - Auto-detection for ~/Mdmailbox/drafts/*.md files
;;   - Preview email with validation (C-c C-p)
;;   - Send email directly from Emacs (C-c C-c)
;;   - Abort/close draft (C-c C-k)
;;   - YAML syntax highlighting
;;
;; Installation:
;;   Manual: (add-to-list 'load-path "~/.emacs.d/lisp/mdmailbox")
;;           (require 'mdmailbox)
;;
;;   DOOM:   Copy emacs/ to ~/.config/doom/modules/lang/mdmailbox/
;;           Add :lang mdmailbox to ~/.config/doom/init.el
;;           Run doom sync
;;
;;   straight.el:
;;           (use-package mdmailbox
;;             :straight (mdmailbox
;;                        :type git
;;                        :host github
;;                        :repo "HeinrichHartmann/mdmailbox"
;;                        :files ("emacs/*.el"))
;;             :mode ("Mdmailbox/drafts/.*\\.md\\'" . mdmailbox-mode))

;;; Code:

(defgroup mdmailbox nil
  "Major mode for mdmailbox email composition."
  :group 'mail
  :prefix "mdmailbox-")

(defcustom mdmailbox-command "mdmailbox"
  "Path to mdmailbox executable."
  :type 'string
  :group 'mdmailbox)

(defcustom mdmailbox-drafts-dir "~/Mdmailbox/drafts"
  "Default directory for email drafts."
  :type 'directory
  :group 'mdmailbox)

(defvar mdmailbox-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c C-c") 'mdmailbox-send)
    (define-key map (kbd "C-c C-p") 'mdmailbox-preview)
    (define-key map (kbd "C-c C-k") 'mdmailbox-abort)
    map)
  "Keymap for mdmailbox-mode.")

(defvar mdmailbox-mode-syntax-table
  (let ((table (make-syntax-table)))
    table)
  "Syntax table for mdmailbox-mode.")

(defun mdmailbox-preview ()
  "Preview the email with validation.
Calls 'mdmailbox send --dry-run' and displays the output."
  (interactive)
  (let ((file (buffer-file-name)))
    (unless file
      (user-error "Buffer must be visiting a file"))
    (let ((output-buffer (get-buffer-create "*mdmailbox-preview*")))
      (with-current-buffer output-buffer
        (let ((inhibit-read-only t))
          (erase-buffer)
          (let ((exit-code (call-process mdmailbox-command nil t nil "send" "--dry-run" file)))
            (cond
             ((= exit-code 0)
              (message "Preview generated (email ready to send)"))
             ((= exit-code 1)
              (message "Preview shows validation errors"))
             (t
              (message "Error running mdmailbox: %d" exit-code))))
          (compilation-mode)
          (goto-char (point-min))))
      (display-buffer output-buffer '(display-buffer-below-selected . ((window-height . 0.3)))))))

(defun mdmailbox-send ()
  "Send the current email.
Prompts for confirmation, then calls 'mdmailbox send --yes'."
  (interactive)
  (let ((file (buffer-file-name)))
    (unless file
      (user-error "Buffer must be visiting a file"))
    (if (y-or-n-p "Send this email? ")
        (progn
          (let ((output-buffer (get-buffer-create "*mdmailbox-send*")))
            (with-current-buffer output-buffer
              (let ((inhibit-read-only t))
                (erase-buffer)
                (let ((exit-code (call-process mdmailbox-command nil t nil "send" "--yes" file)))
                  (if (= exit-code 0)
                      (progn
                        (message "✓ Email sent!")
                        (compilation-mode))
                    (progn
                      (message "✗ Error sending email")
                      (compilation-mode))))
                (goto-char (point-min))))
            (display-buffer output-buffer '(display-buffer-below-selected . ((window-height . 0.3))))))
      (message "Send cancelled"))))

(defun mdmailbox-abort ()
  "Abort email composition and close buffer.
Prompts for confirmation before discarding unsaved changes."
  (interactive)
  (when (y-or-n-p "Discard this email? ")
    (kill-buffer)))

;;;###autoload
(define-derived-mode mdmailbox-mode text-mode "Mdmailbox"
  "Major mode for composing emails with mdmailbox.

Emails are stored as YAML frontmatter followed by Markdown body.

\\{mdmailbox-mode-map}

Key Bindings:
  C-c C-p    Preview email with validation (mdmailbox send --dry-run)
  C-c C-c    Send email (mdmailbox send --yes)
  C-c C-k    Abort composition and close buffer"
  :syntax-table mdmailbox-mode-syntax-table

  ;; Font-locking for YAML frontmatter
  (setq font-lock-defaults
        '((("^---$" . font-lock-comment-face)
           ("^[a-z-]+:" . font-lock-keyword-face)
           ("^[a-z-]+: .*$" . font-lock-string-face))))

  ;; Set fill-column for email bodies
  (setq fill-column 80)

  ;; Mode line
  (setq mode-name "Mdmailbox"))

;;;###autoload
(add-to-list 'auto-mode-alist
             '("Mdmailbox/drafts/.*\\.md\\'" . mdmailbox-mode))

(provide 'mdmailbox)
;;; mdmailbox.el ends here
