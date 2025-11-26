/*
 * YARA Rules for RAG Knowledge Base Malware Detection
 *
 * These rules detect common malware patterns in documents.
 * Customize these rules based on your security requirements.
 */

rule Suspicious_Embedded_Executable {
    meta:
        description = "Detects embedded executables in documents"
        author = "RAG-KB Security"
        severity = "high"

    strings:
        $mz = { 4D 5A }  // MZ header (PE executable)
        $pe = "PE\x00\x00"
        $elf = { 7F 45 4C 46 }  // ELF header

    condition:
        any of them
}

rule Suspicious_VBA_Macros {
    meta:
        description = "Detects suspicious VBA macro patterns"
        author = "RAG-KB Security"
        severity = "medium"

    strings:
        $auto1 = "AutoOpen" nocase
        $auto2 = "AutoExec" nocase
        $auto3 = "Auto_Open" nocase
        $shell = "Shell" nocase
        $wscript = "WScript.Shell" nocase
        $exec = "CreateObject" nocase
        $download = "URLDownloadToFile" nocase

    condition:
        any of ($auto*) and any of ($shell, $wscript, $exec, $download)
}

rule Suspicious_PDF_JavaScript {
    meta:
        description = "Detects potentially malicious JavaScript in PDFs"
        author = "RAG-KB Security"
        severity = "medium"

    strings:
        $js = "/JavaScript"
        $aa = "/AA"  // Automatic actions
        $openaction = "/OpenAction"
        $launch = "/Launch"
        $eval = "eval("
        $unescape = "unescape("

    condition:
        $js and ($aa or $openaction or $launch or $eval or $unescape)
}

rule Embedded_Office_OLE {
    meta:
        description = "Detects embedded OLE objects in documents"
        author = "RAG-KB Security"
        severity = "low"

    strings:
        $ole = { D0 CF 11 E0 A1 B1 1A E1 }  // OLE header
        $package = "Package" nocase
        $embedded = "EmbeddedObject"

    condition:
        $ole and ($package or $embedded)
}

rule Suspicious_Archive_Content {
    meta:
        description = "Detects suspicious files in archives"
        author = "RAG-KB Security"
        severity = "medium"

    strings:
        $exe = ".exe" nocase
        $scr = ".scr" nocase
        $bat = ".bat" nocase
        $cmd = ".cmd" nocase
        $ps1 = ".ps1" nocase
        $vbs = ".vbs" nocase
        $dll = ".dll" nocase

    condition:
        any of them
}

rule Large_Obfuscated_Data {
    meta:
        description = "Detects large chunks of potentially obfuscated data"
        author = "RAG-KB Security"
        severity = "low"

    strings:
        $base64 = /[A-Za-z0-9+\/]{1000,}/  // Long base64-like string
        $hex = /[0-9a-fA-F]{1000,}/        // Long hex string

    condition:
        any of them
}

rule Suspicious_Shellcode {
    meta:
        description = "Detects potential shellcode patterns"
        author = "RAG-KB Security"
        severity = "high"

    strings:
        $nop_sled = { 90 90 90 90 90 90 90 90 }
        $xor_decoder = { 31 ?? 83 ?? ?? 74 }
        $jmp_call = { E8 ?? ?? ?? ?? C3 }

    condition:
        any of them
}
