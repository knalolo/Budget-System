param(
    [Parameter(Mandatory = $true)]
    [string]$FromMailbox,
    [Parameter(Mandatory = $true)]
    [string]$To,
    [string]$Cc = "",
    [Parameter(Mandatory = $true)]
    [string]$Subject,
    [Parameter(Mandatory = $true)]
    [string]$HtmlBodyPath,
    [string]$AttachmentsJson = "[]",
    [switch]$Send,
    [switch]$Display
)

$ErrorActionPreference = "Stop"

function Get-OutlookApplication {
    try {
        return [Runtime.InteropServices.Marshal]::GetActiveObject("Outlook.Application")
    } catch {
        return New-Object -ComObject Outlook.Application
    }
}

try {
    $outlook = Get-OutlookApplication
    $mail = $outlook.CreateItem(0)

    # This sets the From field for a shared mailbox when permission exists.
    $mail.SentOnBehalfOfName = $FromMailbox

    try {
        foreach ($account in $outlook.Session.Accounts) {
            if ($account.SmtpAddress -and ($account.SmtpAddress -ieq $FromMailbox)) {
                $mail.SendUsingAccount = $account
                break
            }
        }
    } catch {
        # Some Outlook profiles do not expose shared mailboxes as accounts.
        # SentOnBehalfOfName can still work when delegated sending is allowed.
    }

    $mail.To = $To
    if ($Cc) {
        $mail.CC = $Cc
    }
    $mail.Subject = $Subject
    $mail.HTMLBody = Get-Content -LiteralPath $HtmlBodyPath -Raw -Encoding UTF8

    if ($AttachmentsJson -and $AttachmentsJson -ne "[]") {
        $attachmentPaths = ConvertFrom-Json -InputObject $AttachmentsJson
        if ($attachmentPaths -is [string]) {
            $attachmentPaths = @($attachmentPaths)
        }
        foreach ($path in $attachmentPaths) {
            if ($path -and (Test-Path -LiteralPath $path)) {
                [void]$mail.Attachments.Add((Resolve-Path -LiteralPath $path).Path)
            } elseif ($path) {
                throw "Attachment not found: $path"
            }
        }
    }

    if ($Send) {
        $mail.Send()
        Write-Host "Sent email from $FromMailbox to $To"
    } else {
        $mail.Save()
        if ($Display) {
            $mail.Display()
            Write-Host "Draft created and opened. Review it in Outlook before sending."
        } else {
            Write-Host "Draft saved. Open Outlook Drafts to review it. Add -Send to send automatically."
        }
    }
} catch {
    Write-Error "Outlook automation failed. Confirm Outlook desktop is open/signed in and that $FromMailbox can send manually. Details: $($_.Exception.Message)"
    exit 1
}
