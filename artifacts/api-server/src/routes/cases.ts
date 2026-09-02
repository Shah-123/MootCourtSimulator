import { Router, type IRouter } from "express";
import { and, eq, desc } from "drizzle-orm";
import { db, casesTable } from "@workspace/db";
import {
  ListCasesQueryParams,
  ListCasesResponse,
  GenerateCaseBody,
  GenerateCaseResponse,
  GetCaseParams,
  GetCaseResponse,
} from "@workspace/api-zod";
import { AiServiceError, generateCase } from "../lib/ai-service";

const router: IRouter = Router();

router.get("/cases", async (req, res): Promise<void> => {
  const query = ListCasesQueryParams.safeParse(req.query);
  if (!query.success) {
    res.status(400).json({ error: query.error.message });
    return;
  }

  const conditions = [];
  if (query.data.areaOfLaw) {
    conditions.push(eq(casesTable.areaOfLaw, query.data.areaOfLaw));
  }
  if (query.data.difficulty) {
    conditions.push(eq(casesTable.difficulty, query.data.difficulty));
  }

  const cases = await db
    .select()
    .from(casesTable)
    .where(conditions.length ? and(...conditions) : undefined)
    .orderBy(desc(casesTable.createdAt));

  res.json(ListCasesResponse.parse(cases));
});

router.post("/cases/generate", async (req, res): Promise<void> => {
  const parsed = GenerateCaseBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const { areaOfLaw, difficulty } = parsed.data;

  req.log.info({ areaOfLaw, difficulty }, "Generating new case");

  // Retrieval, drafting and the citation audit all happen in the AI service.
  // This route validates the request and persists what comes back.
  let generated;
  try {
    generated = await generateCase(areaOfLaw, difficulty);
  } catch (err) {
    req.log.error({ err, areaOfLaw, difficulty }, "Case generation failed");
    // A 422 from the service means the model produced something it refused to
    // hand over — too few grounds survived the audit, or no parties were named.
    // That is a failed generation, not a bad request from the client.
    const status = err instanceof AiServiceError && err.status === 422 ? 502 : 500;
    res.status(status).json({ error: "Failed to generate case" });
    return;
  }

  const { audit } = generated;
  if (audit.hallucinated > 0 || audit.droppedGrounds.length > 0) {
    req.log.warn(
      {
        areaOfLaw,
        hallucinated: audit.hallucinated,
        total: audit.total,
        droppedGrounds: audit.droppedGrounds,
      },
      "Generated case cited provisions that do not exist; " +
        "storing only verified citations and grounds",
    );
  }

  const [created] = await db
    .insert(casesTable)
    .values({
      title: generated.title,
      areaOfLaw,
      difficulty,
      proceedingType: generated.proceedingType,
      summary: generated.summary,
      applicableLaws: generated.applicableLaws,
      petitionerName: generated.petitionerName,
      petitionerRole: generated.petitionerRole,
      respondentName: generated.respondentName,
      respondentRole: generated.respondentRole,
      witnesses: generated.witnesses,
      citations: generated.citations,
      brief: generated.brief,
      source: "generated",
    })
    .returning();

  res.status(201).json(GenerateCaseResponse.parse(created));
});

router.get("/cases/:id", async (req, res): Promise<void> => {
  const params = GetCaseParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [courtCase] = await db
    .select()
    .from(casesTable)
    .where(eq(casesTable.id, params.data.id));

  if (!courtCase) {
    res.status(404).json({ error: "Case not found" });
    return;
  }

  res.json(GetCaseResponse.parse(courtCase));
});

export default router;
