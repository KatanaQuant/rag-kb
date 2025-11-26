/*
 * YARA Rules for RAG Knowledge Base Malware Detection
 *
 * These rules detect malware patterns in documents while minimizing
 * false positives for legitimate PDFs, code files, and ebooks.
 *
 * SEVERITY LEVELS:
 * - high: CRITICAL - should trigger quarantine
 * - medium: WARNING - log and flag for review
 * - low: INFO - informational only
 *
 * NOTE: Rules with severity="high" in combination with dangerous
 * patterns will trigger CRITICAL alerts. Most rules here are tuned
 * for WARNING level to avoid false positives in document KBs.
 */

/*
 * DISABLED: Too many false positives in PDFs
 * PDFs commonly contain MZ headers in embedded fonts and images.
 * Uncomment only if you need strict executable detection.
 *
rule Suspicious_Embedded_Executable {
    meta:
        description = "Detects embedded executables in documents"
        author = "RAG-KB Security"
        severity = "medium"
        false_positive_note = "PDFs often contain MZ headers in embedded fonts"

    strings:
        $mz = { 4D 5A }  // MZ header (PE executable)
        $pe = "PE\x00\x00"
        $elf = { 7F 45 4C 46 }  // ELF header

    condition:
        // Only flag if found near file start (real executables)
        // or if multiple indicators present
        ($mz at 0) or ($elf at 0) or (#mz > 5 and #pe > 1)
}
*/

rule Suspicious_VBA_Macros {
    meta:
        description = "Detects suspicious VBA macro patterns in Office documents"
        author = "RAG-KB Security"
        severity = "medium"

    strings:
        $auto1 = "AutoOpen" nocase
        $auto2 = "AutoExec" nocase
        $auto3 = "Auto_Open" nocase
        $auto4 = "Document_Open" nocase
        $shell = "Shell" nocase
        $wscript = "WScript.Shell" nocase
        $exec = "CreateObject" nocase
        $download = "URLDownloadToFile" nocase
        $powershell = "powershell" nocase

    condition:
        // Require auto-execution trigger + dangerous action
        any of ($auto*) and any of ($shell, $wscript, $exec, $download, $powershell)
}

rule Malicious_PDF_JavaScript {
    meta:
        description = "Detects malicious JavaScript patterns in PDFs"
        author = "RAG-KB Security"
        severity = "medium"

    strings:
        $js = "/JavaScript"
        $launch = "/Launch"
        $eval = "eval(" nocase
        $shellcode = "shellcode" nocase
        $fromcharcode = "fromCharCode" nocase

    condition:
        // Require JavaScript + actual exploit indicators
        $js and ($launch or $shellcode or ($eval and $fromcharcode))
}

/*
 * DISABLED: Too many false positives
 * Office documents legitimately use OLE for embedded content.
 *
rule Embedded_Office_OLE {
    ...
}
*/

/*
 * DISABLED: Causes false positives in code files and documentation
 * Code files legitimately reference .exe, .dll extensions
 *
rule Suspicious_Archive_Content {
    ...
}
*/

/*
 * DISABLED: PDFs use base64 for embedded images/fonts
 * This rule triggers on almost every PDF.
 *
rule Large_Obfuscated_Data {
    ...
}
*/

/*
 * DISABLED: Common byte patterns appear in many PDFs
 * The patterns are too generic for document scanning.
 *
rule Suspicious_Shellcode {
    ...
}
*/

rule Cryptocurrency_Miner {
    meta:
        description = "Detects cryptocurrency mining indicators"
        author = "RAG-KB Security"
        severity = "high"

    strings:
        $stratum = "stratum+tcp://"
        $stratum2 = "stratum+ssl://"
        $xmrig = "xmrig" nocase
        $cryptonight = "cryptonight" nocase
        $coinhive = "coinhive" nocase

    condition:
        any of ($stratum*) or ($xmrig and $cryptonight) or $coinhive
}

rule Suspicious_Script_Download {
    meta:
        description = "Detects curl/wget pipe to shell patterns"
        author = "RAG-KB Security"
        severity = "high"

    strings:
        $curl_bash = /curl\s+[^\n]+\|\s*(ba)?sh/ nocase
        $wget_bash = /wget\s+[^\n]+\|\s*(ba)?sh/ nocase
        $curl_python = /curl\s+[^\n]+\|\s*python/ nocase

    condition:
        any of them
}

rule Reverse_Shell {
    meta:
        description = "Detects reverse shell patterns"
        author = "RAG-KB Security"
        severity = "high"

    strings:
        $bash_i = "bash -i >& /dev/tcp/"
        $nc_e = /nc\s+-e\s+\/bin\/(ba)?sh/
        $python_socket = "socket.socket"
        $python_pty = "pty.spawn"
        $perl_socket = "use Socket"

    condition:
        $bash_i or $nc_e or ($python_socket and $python_pty) or
        ($perl_socket and $nc_e)
}

rule Webshell_Indicators {
    meta:
        description = "Detects common webshell patterns"
        author = "RAG-KB Security"
        severity = "high"

    strings:
        // Simplified patterns to avoid regex complexity
        $php_eval1 = "$_GET" nocase
        $php_eval2 = "$_POST" nocase
        $php_eval3 = "$_REQUEST" nocase
        $php_dangerous1 = "eval(" nocase
        $php_dangerous2 = "system(" nocase
        $php_dangerous3 = "exec(" nocase
        $php_dangerous4 = "passthru(" nocase
        $php_dangerous5 = "shell_exec(" nocase
        $php_base64 = "base64_decode($_" nocase
        $asp_eval = "eval(Request" nocase
        $jsp_runtime = "Runtime.getRuntime().exec" nocase

    condition:
        // PHP webshell: user input + dangerous function
        (any of ($php_eval*) and any of ($php_dangerous*)) or
        $php_base64 or $asp_eval or $jsp_runtime
}
