# mdmailbox.el - Emacs Integration

Major mode for composing and sending emails with mdmailbox directly from Emacs.

## Features

- **Auto-detection**: Automatically enables for `.md` files in `~/Mdmailbox/drafts/`
- **Preview**: `C-c C-p` to preview email with validation
- **Send**: `C-c C-c` to send email with confirmation
- **Abort**: `C-c C-k` to discard draft
- **YAML syntax highlighting**: Highlights email headers
- **CLI integration**: Uses installed `mdmailbox` command

## Installation

### Option 1: Manual (Any Emacs)

1. Copy the `emacs/` directory to `~/.emacs.d/lisp/`:
   ```bash
   mkdir -p ~/.emacs.d/lisp
   cp -r emacs ~/.emacs.d/lisp/mdmailbox
   ```

2. Add to your `~/.emacs.d/init.el`:
   ```elisp
   (add-to-list 'load-path "~/.emacs.d/lisp/mdmailbox")
   (require 'mdmailbox)
   ```

3. Restart Emacs

### Option 2: DOOM Emacs

1. Copy the `emacs/` directory to DOOM's modules:
   ```bash
   mkdir -p ~/.config/doom/modules/lang/mdmailbox
   cp emacs/* ~/.config/doom/modules/lang/mdmailbox/
   ```

2. Create `~/.config/doom/modules/lang/mdmailbox/config.el`:
   ```elisp
   ;;; lang/mdmailbox/config.el -*- lexical-binding: t; -*-

   (use-package! mdmailbox
     :mode ("Mdmailbox/drafts/.*\\.md\\'" . mdmailbox-mode))
   ```

3. Add to `~/.config/doom/init.el`:
   ```elisp
   :lang
   (mdmailbox
     ;; your options
     )
   ```

4. Run:
   ```bash
   doom sync
   ```

### Option 3: straight.el

Add to your `~/.emacs.d/init.el`:

```elisp
(use-package mdmailbox
  :straight (mdmailbox
             :type git
             :host github
             :repo "HeinrichHartmann/mdmailbox"
             :files ("emacs/*.el"))
  :mode ("Mdmailbox/drafts/.*\\.md\\'" . mdmailbox-mode)
  :custom
  (mdmailbox-command "mdmailbox")
  (mdmailbox-drafts-dir "~/Mdmailbox/drafts"))
```

## Usage

### Writing a Draft

1. Open any `.md` file in `~/Mdmailbox/drafts/`:
   ```bash
   emacs ~/Mdmailbox/drafts/hello.md
   ```

2. `mdmailbox-mode` automatically loads (check mode line)

3. Edit YAML headers and body:
   ```yaml
   ---
   from: you@example.com
   to: recipient@example.com
   subject: Hello
   attachments:
     - ./report.pdf
   ---

   Hi there!

   This is the email body.
   ```

### Previewing

Press `C-c C-p` to show validation preview in `*mdmailbox-preview*` buffer:

```
══════════════════════════════════════════════════════════════════
 From:       you@example.com ✓ credentials found
 To:         recipient@example.com ✓ valid
 Subject:    Hello ✓ 5 chars
 Attachments: 1 file(s)
             report.pdf ✓ 2.3 MB, application/pdf
──────────────────────────────────────────────────────────────────

Hi there!

This is the email body.

══════════════════════════════════════════
✓ All headers valid
```

### Sending

Press `C-c C-c` to send:

1. Prompted for confirmation: `Send this email? (y or n)`
2. Results displayed in `*mdmailbox-send*` buffer
3. On success, email moved to `~/Mdmailbox/sent/`

### Aborting

Press `C-c C-k` to discard draft:

1. Prompted for confirmation: `Discard this email? (y or n)`
2. Buffer closes (draft file remains on disk)

## Configuration

Customize via `M-x customize-group RET mdmailbox RET` or in your init.el:

```elisp
(setq mdmailbox-command "/usr/local/bin/mdmailbox")  ; Custom mdmailbox path
(setq mdmailbox-drafts-dir "~/MyEmail/drafts")        ; Custom drafts directory
```

## Requirements

- **Emacs 27.1+** (for `lexical-binding`)
- **mdmailbox** command on PATH (install via `pip install mdmailbox` or `uv tool install mdmailbox`)
- **~/.authinfo** with SMTP credentials configured

## Keybindings

| Keybinding | Command | Description |
|---|---|---|
| `C-c C-p` | `mdmailbox-preview` | Preview email with validation |
| `C-c C-c` | `mdmailbox-send` | Send email after confirmation |
| `C-c C-k` | `mdmailbox-abort` | Discard draft and close buffer |

## Troubleshooting

### Mode doesn't auto-load

Check that:
1. File path contains `Mdmailbox/drafts/`
2. File extension is `.md`
3. Mode is installed correctly

Manual enable: `M-x mdmailbox-mode`

### "mdmailbox: command not found"

Ensure mdmailbox is installed:
```bash
# Via pip
pip install mdmailbox

# Via uv
uv tool install mdmailbox
```

Check PATH:
```elisp
(message (getenv "PATH"))
```

### Preview/send produces no output

Check `*Messages*` buffer for error details. Common issues:
- SMTP credentials not in `~/.authinfo`
- Invalid email headers (see validation output)
- Email file not properly formatted

## Examples

### Simple Email

```yaml
---
from: me@example.com
to: friend@example.com
subject: Coffee tomorrow?
---

Hey!

Are we still on for coffee tomorrow at 10?

Thanks!
```

### Email with Attachments

```yaml
---
from: me@example.com
to: boss@example.com
subject: Q4 Report
attachments:
  - ./q4-report.pdf
  - ~/reports/metrics.xlsx
---

Please find attached the Q4 report and metrics.

Best regards
```

### Reply to Email

```yaml
---
from: me@example.com
to: alice@example.com
subject: Re: Project Status
in-reply-to: <abc123@example.com>
---

Thanks for the update, Alice.

I agree with your approach.
```

## Development

The mdmailbox.el file is self-contained and requires no external Emacs packages.

To test:
1. Load the file: `M-x load-file emacs/mdmailbox.el`
2. Create a test email: `C-x C-f ~/Mdmailbox/drafts/test.md`
3. Edit headers and body
4. Test commands: `C-c C-p` (preview), `C-c C-c` (send), `C-c C-k` (abort)

## License

MIT (same as mdmailbox)

## See Also

- [mdmailbox README](../README.md) - Main project documentation
- [mdmailbox CLI Reference](../README.md#commands) - Available commands
- [DOOM Emacs Documentation](https://docs.doomemacs.org/) - DOOM-specific setup
