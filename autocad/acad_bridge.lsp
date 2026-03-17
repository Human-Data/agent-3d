;;; Claude Bridge - run an AutoLISP file inside AutoCAD and report back.
;;;
;;; acad_run.py types this at the command line:
;;;   (progn (load "<this file>") (claude-run "<cmd.lsp>" "<result.txt>"))
;;;
;;; Result file: line 1 = OK | ERROR, then everything the script printed to the
;;; command line (captured via LOGFILEMODE), then "=> <value of last expression>"
;;; or the error message. Written to <result>.tmp and renamed, so it is never
;;; read half-written.

(vl-load-com)

(defun claude-run (cmd res / was lg skip val lf f line tmp)
  (setq was (getvar "LOGFILEMODE"))
  (setvar "LOGFILEMODE" 1)                       ; text window -> log file (princ, print, command echo)
  (setq lg   (getvar "LOGFILENAME")
        skip (if (and lg (findfile lg)) (vl-file-size lg) 0))   ; ignore anything already in the log
  (setq val (vl-catch-all-apply 'load (list cmd)))
  (command)                                      ; cancel any command the script left pending
  (setvar "LOGFILEMODE" 0)                       ; flush + close the log
  (setq tmp (strcat res ".tmp")
        f   (open tmp "w"))
  (write-line (if (vl-catch-all-error-p val) "ERROR" "OK") f)
  (if (and lg (setq lf (open lg "r")))
    (progn
      (repeat skip (read-char lf))
      (while (setq line (read-line lf)) (write-line line f))
      (close lf)
      (vl-file-delete lg)))
  (write-line (if (vl-catch-all-error-p val)
                (vl-catch-all-error-message val)
                (strcat "=> " (vl-prin1-to-string val)))
              f)
  (close f)
  (vl-file-rename tmp res)
  (vl-file-delete cmd)
  (if (/= was 0) (setvar "LOGFILEMODE" was))     ; restore the user's own logging
  (princ))
