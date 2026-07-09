package custom;
import java.util.Random;
import robocode.AdvancedRobot;
import robocode.HitByBulletEvent;
import robocode.HitRobotEvent;
import robocode.ScannedRobotEvent;
import robocode.BulletHitEvent;

public class MyTank extends AdvancedRobot {

    private Random random = new Random();
    private String lastScannedRobot = null;
    private double lastScannedBearing = 0;
    private double lastScannedDistance = 0;
    private double lastScannedEnergy = 0;
    private long lastScanTime = 0;

    @Override
    public void run() {
        setAdjustRadarForRobotTurn(true);
        setAdjustGunForRobotTurn(true);

        while (true) {
            setTurnRadarRight(360); // Keep scanning
            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        lastScannedRobot = e.getName();
        lastScannedBearing = e.getBearing();
        lastScannedDistance = e.getDistance();
        lastScannedEnergy = e.getEnergy();
        lastScanTime = getTime();

        // Enhanced targeting with lead prediction
        double bulletPower = Math.min(3.0, Math.max(0.1, 400 - lastScannedDistance) / 100);
        double myX = getX();
        double myY = getY();
        double enemyX = myX + lastScannedDistance * Math.sin(Math.toRadians(getHeading() + lastScannedBearing));
        double enemyY = myY + lastScannedDistance * Math.cos(Math.toRadians(getHeading() + lastScannedBearing));
        
        // Predict enemy position based on bearing and distance
        double enemyHeading = e.getHeading();
        double enemyVelocity = e.getVelocity();
        
        // Simple prediction: assume enemy continues in same direction
        // Calculate time for bullet to reach enemy and where enemy will be
        double bulletSpeed = 20 - 3 * bulletPower;
        double timeToHit = lastScannedDistance / bulletSpeed;
        
        // Predict where enemy will be when bullet arrives
        double predictedX = enemyX + Math.sin(Math.toRadians(enemyHeading)) * enemyVelocity * timeToHit;
        double predictedY = enemyY + Math.cos(Math.toRadians(enemyHeading)) * enemyVelocity * timeToHit;
        
        // Calculate the angle to the predicted position
        double absoluteBearing = Math.toDegrees(Math.atan2(predictedX - myX, predictedY - myY));
        double gunTurn = absoluteBearing - getGunHeading();
        
        // Normalize the turn angle
        while (gunTurn > 180) gunTurn -= 360;
        while (gunTurn < -180) gunTurn += 360;
        
        setTurnGunRight(gunTurn);
        setFire(bulletPower);

        // Enhanced movement - more unpredictable
        // If enemy is close, move erratically
        if (lastScannedDistance < 150) {
            // Move perpendicular to enemy but randomly switch direction
            double moveAngle = e.getBearing() + 90 + (random.nextBoolean() ? 0 : 180);
            setTurnRight(moveAngle + (random.nextDouble() - 0.5) * 45); // Add some randomness
            setAhead(100 + random.nextDouble() * 100); // Vary the distance
        } 
        // If enemy is far, approach but with zigzag pattern
        else if (lastScannedDistance > 300) {
            double moveAngle = e.getBearing() + (random.nextDouble() - 0.5) * 30; // Slight angle variation
            setTurnRight(moveAngle);
            setAhead(100);
        } 
        // If at medium range, circle strafe
        else {
            // Circle strafe around the enemy with random direction
            int direction = random.nextBoolean() ? 1 : -1;
            setTurnRight(e.getBearing() + 90 * direction + (random.nextDouble() - 0.5) * 30);
            setAhead(50 + random.nextDouble() * 50);
        }

        execute();
    }

    @Override
    public void onHitByBullet(HitByBulletEvent e) {
        // When hit, move unpredictably to avoid being hit again
        setTurnRight(90 + (random.nextDouble() - 0.5) * 180); // Random turn between 0 and 180
        setAhead(50 + random.nextDouble() * 100); // Random distance
        execute();
    }

    @Override
    public void onHitRobot(HitRobotEvent e) {
        // Move away when hitting another robot, but in a random direction
        setTurnRight(180 + (random.nextDouble() - 0.5) * 90); // Turn around with some randomness
        setBack(100);
        execute();
    }

    @Override
    public void onBulletHit(BulletHitEvent e) {
        // If we hit, continue the same strategy but adjust power based on remaining enemy health
        double bulletPower = Math.min(3.0, Math.max(0.1, 300 - lastScannedDistance) / 100);
        if (lastScannedDistance < 300) {
            setTurnGunRight(lastScannedBearing);
            setFire(bulletPower);
        }
        execute();
    }
}