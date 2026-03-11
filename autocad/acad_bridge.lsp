;;; Claude Bridge - run an AutoLISP file inside AutoCAD and report back.
;;;
;;; acad_run.py types this at the command line:
;;;   (progn (load "<this file>") (claude-run "<cmd.lsp>" "<result.txt>"))
;;;
;;; Result file: line 1 = OK | ERROR, then "=> <value of last expression>" or the
;;; error message. Written to <result>.tmp and renamed, so it is never read
;;; half-written.

(vl-load-com)

(defun claude-run (cmd res / val f tmp)
  (setq val (vl-catch-all-apply 'load (list cmd)))
  (setq tmp (strcat res ".tmp")
        f   (open tmp "w"))
  (write-line (if (vl-catch-all-error-p val) "ERROR" "OK") f)
  (write-line (if (vl-catch-all-error-p val)
                (vl-catch-all-error-message val)
                (strcat "=> " (vl-prin1-to-string val)))
              f)
  (close f)
  (vl-file-rename tmp res)
  (vl-file-delete cmd)
  (princ))
