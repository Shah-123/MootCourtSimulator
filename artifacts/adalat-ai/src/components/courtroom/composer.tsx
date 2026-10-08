import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getGetSessionQueryKey,
  useSendCourtroomTurn,
} from "@workspace/api-client-react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getErrorMessage } from "@/components/api-state";
import { useToast } from "@/hooks/use-toast";

/**
 * Addressing the court in writing.
 *
 * `POST /sessions/:id/turn` has existed since the courtroom graph landed and
 * the web app had never called it — the interface was voice-only, so a student
 * without a working microphone, or presenting from a laptop in a room with no
 * quiet corner, had no way to argue at all. This is the same graph the voice
 * path runs (`run_turn` is defined in terms of `run_turn_stream`), so a written
 * turn and a spoken one reach the same agents and the same audit.
 *
 * Who answers is the supervisor's decision, not this dialog's: it does not
 * choose a recipient, and the copy says so rather than implying the student is
 * picking who replies.
 */
export function AddressComposer({
  sessionId,
  open,
  onOpenChange,
  witnessOnStand,
}: {
  sessionId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  witnessOnStand: string | null;
}) {
  const [utterance, setUtterance] = useState("");
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { mutate, isPending } = useSendCourtroomTurn();

  const handleSubmit = () => {
    const text = utterance.trim();
    if (!text) return;

    mutate(
      { id: sessionId, data: { utterance: text } },
      {
        onSuccess: (result) => {
          queryClient.setQueryData(
            getGetSessionQueryKey(sessionId),
            result.session,
          );
          setUtterance("");
          onOpenChange(false);
        },
        onError: (error) => {
          toast({
            variant: "destructive",
            title: "The court did not receive that",
            description: getErrorMessage(error),
          });
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle className="display-sm text-left">
            {witnessOnStand ? "Put a question" : "Address the court"}
          </DialogTitle>
          <DialogDescription className="text-left font-serif">
            {witnessOnStand
              ? `${witnessOnStand} is in the box. Ask your question as you would from the rostrum — opposing counsel may object before it is answered.`
              : "Make your submission as you would on your feet. This runs the same courtroom as the microphone does; the bench, opposing counsel and any witness decide among themselves who answers."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-1">
          <label htmlFor="address-utterance" className="apparatus text-muted-foreground">
            What you say
          </label>
          <Textarea
            id="address-utterance"
            value={utterance}
            onChange={(event) => setUtterance(event.target.value)}
            placeholder={
              witnessOnStand
                ? "Mr Arif, you have told this court that you were present at the shop that evening. At what time did you arrive?"
                : "My Lord, the petition is maintainable under Article 199 of the Constitution, and I say so for three reasons…"
            }
            className="min-h-[140px] resize-none rounded-sm font-serif leading-relaxed"
            autoFocus
          />
          <p className="apparatus text-muted-foreground/70">
            Every citation you make is checked against the corpus
          </p>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!utterance.trim() || isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            <span>{isPending ? "The court is considering" : "Say it to the court"}</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
