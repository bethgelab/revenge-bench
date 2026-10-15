package custom;

import robocode.*;
import robocode.util.Utils;

import java.awt.*;
import java.util.HashMap;
import java.util.Map;

public class MyTank extends AdvancedRobot {
    private int moveDirection = 1;
    private static final double WALL_MARGIN = 60;

    // Target tracking for circular/linear targeting
    private String targetName = null;
    private double lastEnemyHeading = 0;
    private long lastScanTime = -1;
    private boolean hasPrevScan = false;
    private double lastDistance = Double.POSITIVE_INFINITY;

    // Per-target energy and hit-rate tracking
    private final Map<String, Double> energyByName = new HashMap<>();
    private final Map<String, Double> hitEwmaByName = new HashMap<>();
    private final Map<String, Long> lastSeenTickByName = new HashMap<>();

    // Virtual guns: per-target EWMA performance [0]=circular, [1]=linear, [2]=head-on, [3]=lin-solver
    private final Map<String, double[]> vgEwmaByName = new HashMap<>();
    private static final int GUN_CIRC = 0;
    private static final int GUN_LIN = 1;
    private static final int GUN_HO = 2;
    private static final int GUN_LINSOLVE = 3;
    private static final double VG_ALPHA = 0.12;

    // Track bullets to update virtual-gun stats on result
    private static class ShotInfo {
        final String target;
        final int gunIndex;
        ShotInfo(String target, int gunIndex) { this.target = target; this.gunIndex = gunIndex; }
    }
    private final Map<Bullet, ShotInfo> bulletInfo = new HashMap<>();

    // Track enemy energy to detect bullet fire (energy drop of ~0.1..3.0)
    private double lastEnemyEnergy = -1; // kept for backward compat; not used for detection anymore
    private long lastDodgeTime = -999;

    // Movement randomization
    private double orbitJitter = 0.0;
    private long lastOrbitJitterTime = 0;

    private static final double RADAR_MIN_OVERSHOOT = Math.toRadians(2);

    // Firing statistics (EWMA hit rate) - global baseline
    private int shotsFired = 0;
    private double hitRateEwma = 0.30; // start neutral
    private static final double HIT_EWMA_ALPHA = 0.15;

    // Misc movement timers
    private long lastDirectionFlipTime = 0;

    @Override
    public void run() {
        setAdjustRadarForGunTurn(true);
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForRobotTurn(true);

        setBodyColor(Color.DARK_GRAY);
        setGunColor(Color.ORANGE);
        setRadarColor(Color.BLACK);
        setBulletColor(Color.YELLOW);
        setScanColor(Color.RED);

        // Initial radar sweep to find enemies
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);

        while (true) {
            // Simple wall awareness: flip direction if we are near a wall
            if (isNearWall()) {
                moveDirection = -moveDirection;
                lastDirectionFlipTime = getTime();
            }

            // Periodically randomize orbit offset to avoid pattern locking
            if (getTime() - lastOrbitJitterTime > 25) {
                orbitJitter = (Math.random() - 0.5) * 0.6; // ~[-0.3, 0.3] rad
                lastOrbitJitterTime = getTime();
            }

            // Slightly vary max velocity to avoid being too predictable
            double vel = 7.5 + (Math.random() * 1.0) - 0.5; // ~[7.0, 8.5]
            setMaxVelocity(vel);

            // If we have not scanned recently, sweep radar and keep moving to search
            if (!hasPrevScan || (getTime() - lastScanTime > 16)) {
                setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
                setAhead(100 * moveDirection);
            }
            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        // Select/keep closest or current target
        if (targetName == null || e.getName().equals(targetName) || e.getDistance() + 50 < lastDistance) {
            targetName = e.getName();
            lastDistance = e.getDistance();
        } else if (!e.getName().equals(targetName)) {
            // Not our primary target; still update recency for potential switching
        }

        // Compute absolute bearing and enemy coordinates
        double absBearing = getHeadingRadians() + e.getBearingRadians();
        double enemyX = getX() + Math.sin(absBearing) * e.getDistance();
        double enemyY = getY() + Math.cos(absBearing) * e.getDistance();

        // Keep radar locked with strong 2x turn and slight overshoot
        double radarTurn = Utils.normalRelativeAngle(absBearing - getRadarHeadingRadians());
        setTurnRadarRightRadians(radarTurn * 2.0 + Math.copySign(RADAR_MIN_OVERSHOOT, radarTurn));

        // Movement: orbit the enemy roughly perpendicular with jitter and wall smoothing
        double distance = e.getDistance();

        // Enemy fire detection (energy drop) - per target
        double prevEnergy = energyByName.getOrDefault(e.getName(), e.getEnergy());
        double energyDrop = prevEnergy - e.getEnergy();
        boolean likelyFired = energyDrop >= 0.1 && energyDrop <= 3.0;

        // If enemy likely fired recently, perform an evasive maneuver (flip/jitter), throttled
        if (likelyFired && (getTime() - lastDodgeTime > 8)) {
            if (Math.random() < 0.65) {
                moveDirection = -moveDirection;
                lastDirectionFlipTime = getTime();
            }
            orbitJitter = (Math.random() - 0.5) * 0.8;
            setAhead((Math.random() < 0.5 ? 1 : -1) * (100 + Math.random() * 80));
            lastDodgeTime = getTime();
        }

        double desired = absBearing + (Math.PI / 2 + orbitJitter) * moveDirection;

        // Anti-ram: if enemy is heading toward us and close, bias strongly laterally and flip if needed
        double enemyHeading = e.getHeadingRadians();
        double enemyVelocity = e.getVelocity();
        double angleToMe = Math.atan2(getX() - enemyX, getY() - enemyY);
        double enemyToMeAngleDiff = Math.abs(Utils.normalRelativeAngle(enemyHeading - angleToMe));
        if (distance < 140 && enemyVelocity > 0.1 && enemyToMeAngleDiff < Math.toRadians(15)) {
            // Hard lateral dodge and direction flip throttled
            if (getTime() - lastDirectionFlipTime > 10) {
                moveDirection = -moveDirection;
                lastDirectionFlipTime = getTime();
            }
            desired = absBearing + (Math.PI / 2) * moveDirection + Math.copySign(Math.toRadians(35), moveDirection);
        }

        // Continuous distance management: nudge orbit angle to maintain ~420 distance
        double targetDist = 420.0;
        double err = (distance - targetDist) / targetDist; // >0 means too far
        double distAdj = clamp(err, -1.0, 1.0) * Math.toRadians(22); // up to ~22 deg of adjustment
        // If too far, turn slightly toward enemy (-moveDirection). If too close, away (+moveDirection).
        desired = Utils.normalRelativeAngle(desired - moveDirection * distAdj);

        // Legacy biasing: small tweaks at extremes (kept but reduced)
        if (distance < 160) {
            desired = Utils.normalRelativeAngle(desired + moveDirection * Math.toRadians(15));
        } else if (distance > 600) {
            desired = Utils.normalRelativeAngle(desired - moveDirection * Math.toRadians(10));
        }

        desired = wallSmoothing(desired, getX(), getY());
        double marginDist = Math.min(Math.min(getX() - WALL_MARGIN, getBattleFieldWidth() - WALL_MARGIN - getX()), Math.min(getY() - WALL_MARGIN, getBattleFieldHeight() - WALL_MARGIN - getY()));
        if (marginDist < 180) {
            double cx = getBattleFieldWidth() / 2.0, cy = getBattleFieldHeight() / 2.0;
            double angCenter = Math.atan2(cx - getX(), cy - getY());
            double tCenter = clamp((180 - marginDist) / 180.0, 0.0, 1.0) * 0.35;
            desired = blendAngle(desired, angCenter, tCenter);
        }

        setTurnRightRadians(Utils.normalRelativeAngle(desired - getHeadingRadians()));

        // Stop-and-go jitter at closer ranges to break linear aim
        if (distance < 260 && Math.random() < 0.06) {
            setAhead((Math.random() < 0.5 ? 1 : -1) * 80);
        } else {
            double move = (distance > 240 ? 1 : -1) * 150 * moveDirection;
            setAhead(move);
        }

        // Adaptive firepower based on distance, energy, and recent hit rate (per-target aware)
        double basePower = Math.min(3.0, Math.max(0.35, 360.0 / (distance + 40.0)));
        if (getEnergy() < 15) basePower = Math.min(basePower, 1.1);
        if (e.getEnergy() < 15) basePower = Math.min(2.0, basePower);

        double hrGlobal = clamp(hitRateEwma, 0.0, 1.0);
        double hrTarget = clamp(hitEwmaByName.getOrDefault(e.getName(), hitRateEwma), 0.0, 1.0);

        // Adjust by target-specific hit rate primarily; fallback to global
        double hrBlend = 0.7 * hrTarget + 0.3 * hrGlobal;
        if (hrBlend < 0.18) basePower *= 0.8;
        else if (hrBlend > 0.42) basePower = Math.min(3.0, basePower * 1.1);

        double bulletPower = Math.max(0.1, Math.min(3.0, basePower));
        double bulletSpeed = 20 - 3 * bulletPower;

        // Targeting predictions
        long dtTicks = (hasPrevScan && targetName != null && targetName.equals(e.getName()))
                ? getTime() - lastScanTime : 0;
        double turnRate = 0;
        if (dtTicks > 0) {
            turnRate = Utils.normalRelativeAngle(enemyHeading - lastEnemyHeading) / dtTicks;
        }

        double bfW = getBattleFieldWidth(), bfH = getBattleFieldHeight();

        // Baseline current enemy position
        double px0 = enemyX;
        double py0 = enemyY;

        // Circular prediction
        double cpx = px0, cpy = py0, ch = enemyHeading;
        double tCirc = 0;
        while ((tCirc * bulletSpeed) < distance && tCirc < 80) {
            ch += turnRate; // constant turn rate
            cpx += Math.sin(ch) * enemyVelocity;
            cpy += Math.cos(ch) * enemyVelocity;

            // Reflect off margins and clamp
            if (cpx < WALL_MARGIN || cpx > bfW - WALL_MARGIN) {
                ch = Math.PI - ch;
                cpx = Math.min(Math.max(cpx, WALL_MARGIN), bfW - WALL_MARGIN);
            }
            if (cpy < WALL_MARGIN || cpy > bfH - WALL_MARGIN) {
                ch = -ch;
                cpy = Math.min(Math.max(cpy, WALL_MARGIN), bfH - WALL_MARGIN);
            }
            tCirc++;
        }

        // Linear prediction (step)
        double lpx = px0, lpy = py0;
        double dT = 0.0;
        double lHeading = enemyHeading;
        while ((dT * bulletSpeed) < distance && dT < 60) {
            lpx += Math.sin(lHeading) * enemyVelocity;
            lpy += Math.cos(lHeading) * enemyVelocity;

            if (lpx < WALL_MARGIN || lpx > bfW - WALL_MARGIN) {
                lHeading = Math.PI - lHeading;
            }
            if (lpy < WALL_MARGIN || lpy > bfH - WALL_MARGIN) {
                lHeading = -lHeading;
            }
            dT++;
        }

        // Analytical linear-intercept prediction (constant velocity)
        double evx = enemyVelocity * Math.sin(enemyHeading);
        double evy = enemyVelocity * Math.cos(enemyHeading);
        double[] linSolvePt = solveLinearIntercept(getX(), getY(), px0, py0, evx, evy, bulletSpeed);
        boolean linSolveValid = (linSolvePt != null)
                && linSolvePt[0] >= WALL_MARGIN && linSolvePt[0] <= bfW - WALL_MARGIN
                && linSolvePt[1] >= WALL_MARGIN && linSolvePt[1] <= bfH - WALL_MARGIN;

        // Compute base weights: prefer circular when enemy turn rate is significant; modulated by lateral velocity
        double turnMag = Math.min(1.0, Math.abs(turnRate) / 0.35); // ~0..1
        double wCirc = clamp(0.15 + 0.85 * turnMag, 0, 1);
        double wLin = 1.0 - wCirc;

        double lateralVelocity = enemyVelocity * Math.sin(enemyHeading - absBearing);
        double lvMag = Math.min(1.0, Math.abs(lateralVelocity) / 8.0);
        wLin += 0.20 * lvMag;
        wCirc += 0.20 * (1.0 - lvMag);
        double wHO = 0.10;
        wHO += 0.45 * (1.0 - lvMag);
        double speedMag = Math.min(1.0, Math.abs(enemyVelocity) / 8.0);
        wHO += 0.25 * (1.0 - speedMag);
        if (distance < 220) wHO += 0.20;

        // New: analytical linear-intercept gun weight (slightly boosted when lateral is strong)
        double wLinSolve = wLin * (0.95 + 0.25 * lvMag);
        if (!linSolveValid) {
            wLinSolve = 0.0;
        }

        // Adjust weights by global hit rate (if we are doing poorly, lean a bit more linear)
        double hr = clamp(hitRateEwma, 0.0, 1.0);
        wCirc *= (0.6 + 0.8 * hr);
        wLin  *= (1.4 - 0.8 * hr);
        wLinSolve *= (1.35 - 0.7 * hr); // similar tendency as linear

        // Virtual-gun performance adjustment per target
        double[] vg = ensureVg(e.getName(), 4);
        double perfCirc = clamp(vg[GUN_CIRC], 0.0, 1.0);
        double perfLin  = clamp(vg[GUN_LIN], 0.0, 1.0);
        double perfHO   = clamp(vg[GUN_HO], 0.0, 1.0);
        double perfLinSolve = clamp(vg[GUN_LINSOLVE], 0.0, 1.0);

        // Boost weights by performance
        wCirc *= (0.7 + 0.6 * perfCirc);
        wLin  *= (0.7 + 0.6 * perfLin);
        wHO   *= (0.7 + 0.6 * perfHO);
        wLinSolve *= (0.7 + 0.6 * perfLinSolve);

        // Normalize guard and choose single best gun (virtual-gun selection)
        if (wCirc < 1e-9 && wLin < 1e-9 && wHO < 1e-9 && wLinSolve < 1e-9) { wCirc = wLin = wHO = wLinSolve = 1.0; }
        double aimAngleCirc = Math.atan2(cpx - getX(), cpy - getY());
        double aimAngleLin  = Math.atan2(lpx - getX(), lpy - getY());
        double aimAngleHO   = absBearing;
        double aimAngleLinSolve = linSolveValid ? Math.atan2(linSolvePt[0] - getX(), linSolvePt[1] - getY()) : aimAngleLin;

        int chosenGun = GUN_CIRC;
        double aimAngle = aimAngleCirc;
        double perfChosen = perfCirc;
        double maxW = wCirc;

        if (wLin > maxW) { maxW = wLin; chosenGun = GUN_LIN; aimAngle = aimAngleLin; perfChosen = perfLin; }
        if (wHO > maxW) { maxW = wHO; chosenGun = GUN_HO; aimAngle = aimAngleHO; perfChosen = perfHO; }
        if (wLinSolve > maxW) { maxW = wLinSolve; chosenGun = GUN_LINSOLVE; aimAngle = aimAngleLinSolve; perfChosen = perfLinSolve; }

        double gunTurn = Utils.normalRelativeAngle(aimAngle - getGunHeadingRadians());
        setTurnGunRightRadians(gunTurn);

        // Fire when the gun is roughly aligned and ready; tolerance scales with distance
        double baseTol = Math.toRadians(3) + Math.min(Math.toRadians(12), Math.toRadians(distance / 60.0));
        // Tighten tolerance slightly if our per-target hit rate is poor (avoid wasting energy)
        double aimTightFactor = (hrBlend < 0.20 ? 0.85 : 1.0) * (0.9 + 0.2 * perfChosen);
        double aimTolerance = baseTol * aimTightFactor;

        if (getGunHeat() == 0 && Math.abs(gunTurn) < aimTolerance) {
            if (getEnergy() > 0.2) {
                Bullet b = setFireBullet(bulletPower);
                if (b != null) {
                    bulletInfo.put(b, new ShotInfo(e.getName(), chosenGun));
                }
                shotsFired++;
            }
        }

        // Save for next scan
        lastEnemyHeading = e.getHeadingRadians();
        lastScanTime = getTime();
        hasPrevScan = true;
        lastDistance = e.getDistance();

        // Update per-target energy and decay-initialize hit ewma if new
        energyByName.put(e.getName(), e.getEnergy());
        hitEwmaByName.putIfAbsent(e.getName(), hitRateEwma);
        lastEnemyEnergy = e.getEnergy(); // kept for completeness
        lastSeenTickByName.put(e.getName(), getTime());
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        // Change direction and introduce a fresh jitter to be less predictable
        moveDirection = -moveDirection;
        lastDirectionFlipTime = getTime();
        orbitJitter = (Math.random() - 0.5) * 0.8;
        setAhead(120 * moveDirection);
        setTurnRight((Math.random() > 0.5 ? 1 : -1) * 40);
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        moveDirection = -moveDirection;
        lastDirectionFlipTime = getTime();
        setBack(120);
        // Nudge heading away from wall
        setTurnRight((Math.random() > 0.5 ? 1 : -1) * 45);
    }

    @Override
    public void onRobotDeath(RobotDeathEvent e) {
        if (e.getName().equals(targetName)) {
            targetName = null;
            lastDistance = Double.POSITIVE_INFINITY;
            lastEnemyEnergy = -1;
        }
        // Cleanup per-target caches
        energyByName.remove(e.getName());
        // Do not remove hitEwmaByName to preserve knowledge across rounds (Robocode resets each battle anyway)
        // Resume sweeping to reacquire next target
        setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
    }

    @Override
    public void onBulletHit(BulletHitEvent event) {
        // Update global EWMA hit rate positively
        hitRateEwma = (1.0 - HIT_EWMA_ALPHA) * hitRateEwma + HIT_EWMA_ALPHA * 1.0;
        // Update per-target EWMA more strongly
        String name = event.getName();
        double cur = hitEwmaByName.getOrDefault(name, hitRateEwma);
        double updated = (1.0 - HIT_EWMA_ALPHA) * cur + HIT_EWMA_ALPHA * 1.0;
        hitEwmaByName.put(name, updated);

        // Update virtual gun stats for this bullet
        ShotInfo info = bulletInfo.remove(event.getBullet());
        if (info != null) {
            double[] vg = ensureVg(info.target, 4);
            vg[info.gunIndex] = (1.0 - VG_ALPHA) * vg[info.gunIndex] + VG_ALPHA * 1.0;
        }
    }

    @Override
    public void onBulletMissed(BulletMissedEvent event) {
        // Update EWMA hit rate negatively
        hitRateEwma = (1.0 - HIT_EWMA_ALPHA) * hitRateEwma + HIT_EWMA_ALPHA * 0.0;

        // Update virtual gun stats for this bullet (miss)
        ShotInfo info = bulletInfo.remove(event.getBullet());
        if (info != null) {
            double[] vg = ensureVg(info.target, 4);
            vg[info.gunIndex] = (1.0 - VG_ALPHA) * vg[info.gunIndex] + VG_ALPHA * 0.0;
        }
    }

    @Override
    public void onBulletHitBullet(BulletHitBulletEvent event) {
        // Treat bullet-bullet collisions as near-miss
        hitRateEwma = (1.0 - HIT_EWMA_ALPHA) * hitRateEwma + HIT_EWMA_ALPHA * 0.25;

        // Update virtual guns as partial success
        ShotInfo info = bulletInfo.remove(event.getBullet());
        if (info != null) {
            double[] vg = ensureVg(info.target, 4);
            vg[info.gunIndex] = (1.0 - VG_ALPHA) * vg[info.gunIndex] + VG_ALPHA * 0.25;
        }
    }

    private boolean isNearWall() {
        return getX() < WALL_MARGIN || getX() > getBattleFieldWidth() - WALL_MARGIN
            || getY() < WALL_MARGIN || getY() > getBattleFieldHeight() - WALL_MARGIN;
    }

    // Simple wall smoothing: adjust desired angle until a projected step stays within margins
    private double wallSmoothing(double angle, double x, double y) {
        double bfW = getBattleFieldWidth(), bfH = getBattleFieldHeight();
        double test = angle;
        int i = 0;
        while (i < 30) {
            double nx = x + Math.sin(test) * 120;
            double ny = y + Math.cos(test) * 120;
            if (nx > WALL_MARGIN && nx < bfW - WALL_MARGIN && ny > WALL_MARGIN && ny < bfH - WALL_MARGIN) {
                break;
            }
            test += 0.15 * moveDirection; // turn along orbit until safe
            i++;
        }
        return test;
    }

    private static double blendAngle(double from, double to, double t) {
        double diff = Utils.normalRelativeAngle(to - from);
        return from + diff * clamp(t, 0.0, 1.0);
    }

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    // Ensure per-target virtual gun EWMA array exists and has at least 'size' elements
    private double[] ensureVg(String name, int size) {
        double[] vg = vgEwmaByName.get(name);
        if (vg == null) {
            vg = new double[size];
            for (int i = 0; i < size; i++) vg[i] = 0.5;
            vgEwmaByName.put(name, vg);
        } else if (vg.length < size) {
            double[] nv = new double[size];
            for (int i = 0; i < size; i++) nv[i] = (i < vg.length ? vg[i] : 0.5);
            vgEwmaByName.put(name, nv);
            vg = nv;
        }
        return vg;
    }

    // Solve for linear intercept point with constant target velocity; returns {ix, iy} or null
    private static double[] solveLinearIntercept(double sx, double sy, double tx, double ty, double tvx, double tvy, double bulletSpeed) {
        double rx = tx - sx;
        double ry = ty - sy;
        double a = tvx * tvx + tvy * tvy - bulletSpeed * bulletSpeed;
        double b = 2.0 * (rx * tvx + ry * tvy);
        double c = rx * rx + ry * ry;

        double t;
        if (Math.abs(a) < 1e-6) {
            if (Math.abs(b) < 1e-6) return null;
            t = -c / b;
        } else {
            double disc = b * b - 4 * a * c;
            if (disc < 0) return null;
            double sqrt = Math.sqrt(disc);
            double t1 = (-b - sqrt) / (2 * a);
            double t2 = (-b + sqrt) / (2 * a);
            t = Math.min(t1, t2);
            if (t < 0) t = Math.max(t1, t2);
        }
        if (t <= 0 || t > 80) return null;
        double ix = tx + tvx * t;
        double iy = ty + tvy * t;
        return new double[]{ix, iy};
    }

    @Override
    public void onHitRobot(HitRobotEvent e) {
        if (e.isMyFault()) {
            setBack(120);
        } else {
            setAhead(120);
        }
        double absBearing = getHeadingRadians() + e.getBearingRadians();
        double desired = Utils.normalRelativeAngle(absBearing + (Math.PI / 2) * (Math.random() < 0.5 ? 1 : -1));
        
        setTurnRightRadians(Utils.normalRelativeAngle(desired - getHeadingRadians()));
        if (getTime() - lastDirectionFlipTime > 8) {
            moveDirection = -moveDirection;
            lastDirectionFlipTime = getTime();
        }
    }
}